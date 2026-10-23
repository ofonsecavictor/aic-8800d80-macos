#!/usr/bin/python3
"""LaunchDaemon and private local control socket for the AIC menu app."""
import json
import ctypes
import os
from pathlib import Path
import signal
import socket
import stat
import subprocess
import threading
import time
from wifi import Wifi
from reports import write_report
from native_radio_control import NativeRadioPublisher, native_interface_name
from native_scan_service import NativeScanSession

HERE=Path(__file__).resolve().parent
SOCKET=Path('/private/tmp/aic-wifi-control.sock')
stop=threading.Event()
native_usb_failure_since=None
native_usb_recovery_attempted=False

def note_native_usb_open_result(error=None):
    """Track the boot-only USB failure that a physical reconnect fixes."""
    global native_usb_failure_since
    if error is None:
        native_usb_failure_since=None
    elif 'Cannot open AIC Wi-Fi interface: e00002bc' in str(error):
        if native_usb_failure_since is None:
            native_usb_failure_since=time.monotonic()
    else:
        native_usb_failure_since=None

def recover_stuck_native_usb():
    """Re-enumerate this dongle once, only after sustained native open errors."""
    global native_usb_recovery_attempted
    if (native_usb_failure_since is None or native_usb_recovery_attempted or
            time.monotonic()-native_usb_failure_since<20):
        return False
    native_usb_recovery_attempted=True
    try:
        library=ctypes.CDLL(str(HERE/'libaicwifi.dylib'))
        library.wifi_reenumerate_verified.restype=ctypes.c_uint32
        result=library.wifi_reenumerate_verified()
        print('AIC: recuperação USB nativa solicitada: %08x'%result,flush=True)
    except (OSError,AttributeError) as error:
        print('AIC: recuperação USB nativa indisponível: '+str(error),flush=True)
    # Allow firmware re-enumeration before another open attempt. The main
    # service never owns the interface when this recovery runs.
    stop.wait(4)
    return True

def publish_capabilities(info):
    """Record only non-identifying firmware limits for native-driver research."""
    keys=('lmac_version','features','max_stations','max_interfaces')
    if not isinstance(info,dict) or any(key not in info for key in keys):return
    try:
        write_report(HERE/'hardware-capabilities.json',
            {key:info[key] for key in keys},mode=0o644)
    except OSError as error:
        print('AIC: diagnóstico de capacidade indisponível: '+str(error),flush=True)

def credential(ssid):
    result=subprocess.run([str(HERE/'aic-wifi-credential'),'--read',ssid],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
    if result.returncode or len(result.stdout)!=32:
        raise RuntimeError('Credencial AIC indisponível no Chaves do Sistema.')
    return result.stdout

def store_credential(ssid,key):
    result=subprocess.run([str(HERE/'aic-wifi-credential'),'--store',ssid],input=key,
        stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=15)
    if result.returncode:raise RuntimeError('Não foi possível guardar a senha do Wi-Fi.')

def optional_radio_bridge():
    try:return NativeRadioPublisher.open_if_present()
    except (OSError,RuntimeError) as error:
        print('AIC: ponte de estado nativo indisponível: '+str(error),flush=True)
        return None

def request_native_power_when_ready(ready, session_stop, timeout=30, retry_delay=2):
    """Give CoreWLAN time to notice a newly registered USB Wi-Fi interface."""
    ready_deadline=time.monotonic()+timeout
    while not ready.is_set() and not session_stop.is_set():
        remaining=ready_deadline-time.monotonic()
        if remaining<=0:return False
        ready.wait(min(.2,remaining))
    if session_stop.is_set():
        return False
    deadline=time.monotonic()+timeout
    last_error=''
    scan_helper=HERE/'aic-native-scan-request'
    while not session_stop.is_set() and time.monotonic()<deadline:
        try:
            interface=native_interface_name()
            if interface is None:
                last_error='interface BSD AIC ainda não registrada'
                remaining=deadline-time.monotonic()
                if remaining<=0 or session_stop.wait(min(retry_delay,remaining)):
                    break
                continue
            result=subprocess.run(
                ['/usr/sbin/networksetup','-setairportpower',interface,'on'],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=10)
            # The successful bounded pilot also asked CoreWLAN to power and
            # scan. networksetup alone can say "Wireless is not available"
            # while the newly registered interface is still coming online.
            if scan_helper.is_file():
                scan=subprocess.run([str(scan_helper),interface],
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                    timeout=max(1,min(30,deadline-time.monotonic())))
                if scan.returncode==0 and not session_stop.is_set():
                    print('AIC: Wi-Fi nativo iniciado e busca CoreWLAN concluída.',flush=True)
                    return True
                last_error=(scan.stderr or scan.stdout).strip()[:200]
            elif result.returncode==0:
                return True
            else:
                last_error=(result.stderr or result.stdout).strip()[:200]
        except (OSError,subprocess.TimeoutExpired) as error:
            last_error=str(error)[:200]
        remaining=deadline-time.monotonic()
        if remaining<=0 or session_stop.wait(min(retry_delay,remaining)):
            break
    if not session_stop.is_set():
        print('AIC: macOS não ativou a interface nativa após novas tentativas: '
              +(last_error or 'sem detalhe'),flush=True)
    return False

def run_native_session_if_available(config, session_stop, on_mode_change=None):
    if not config.get('native_enabled',False):return False
    bridge=optional_radio_bridge()
    if bridge is None:
        print('AIC: controlador nativo ausente; aguardando modo nativo.',flush=True)
        return False
    wifi=None
    power_thread=None
    power_result={'ok':None}
    try:
        wifi=Wifi();wifi.native_stop=session_stop
        note_native_usb_open_result()
        print('AIC: serviço nativo assumiu o dongle.',flush=True)
        ready=threading.Event()
        session=NativeScanSession(
            wifi,bridge,session_stop,
            scan_only=bool(config.get('native_scan_only',False)),ready=ready)
        def enable_native_power():
            try:enabled=request_native_power_when_ready(ready,session_stop)
            except (RuntimeError,OSError,ValueError) as error:
                print('AIC: ativação nativa falhou: '+str(error),flush=True)
                enabled=False
            if not session_stop.is_set():
                power_result['ok']=enabled
                if not enabled:session_stop.set()
        power_thread=threading.Thread(target=enable_native_power,
                                      name='AIC native power-on',daemon=True)
        power_thread.start()
        # Session.run owns Wifi after construction and closes it on exit.
        wifi=None
        if on_mode_change:on_mode_change(True)
        session.run()
        return power_result['ok'] is not False
    except KeyboardInterrupt:
        if power_result['ok'] is False:return False
        raise
    except (RuntimeError,OSError) as error:
        note_native_usb_open_result(error)
        print('AIC: sessão nativa falhou; nova tentativa nativa: '+str(error),flush=True)
        return False
    finally:
        if on_mode_change:on_mode_change(False)
        session_stop.set()
        if power_thread:power_thread.join(10)
        if wifi:wifi.close()
        bridge.close()

def apply_native_power_command(controller, bridge, last_sequence):
    command=bridge.next_power_command()
    if command is None:return last_sequence
    sequence,enabled=command
    if sequence==last_sequence:return last_sequence
    response=controller.handle({'action':'power','enabled':enabled})
    if not response.get('ok'):
        raise RuntimeError('Comando de energia nativo AIC recusado.')
    return sequence

class Controller:
    def __init__(self):
        self.session_stop=None
        self.wake=threading.Event()
        self.lock=threading.Lock()
        self.listener=None
        self.thread=None
        self.native_thread=None
        self.presence_checked=0
        self.presence=False
        self.wifi=None
        self.native_active=False

    def set_native_active(self, value):
        self.native_active=bool(value)

    def config(self):return json.loads((HERE/'profile.json').read_text())
    def save(self,config):write_report(HERE/'profile.json',config,mode=0o600)

    def dongle_present(self):
        now=time.monotonic()
        if now-self.presence_checked<1:return self.presence
        try:
            result=subprocess.run(['/usr/sbin/ioreg','-p','IOUSB','-n','AIC 8800D80','-r','-l'],
                stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=2)
            self.presence=result.returncode==0 and b'"idVendor" = 42652' in result.stdout and b'"idProduct" = 36225' in result.stdout
        except (OSError,subprocess.TimeoutExpired):self.presence=False
        self.presence_checked=now
        return self.presence

    def interrupt(self):
        self.wake.set()
        if self.session_stop:self.session_stop.set()

    def handle(self,value):
        action=value.get('action')
        with self.lock:
            config=self.config()
            if action=='status':
                try:session=json.loads((HERE/'estado-conexao.json').read_text())
                except (OSError,ValueError):session={}
                connected=bool(session.get('active',False))
                present=self.dongle_present()
                return {'ok':True,'enabled':bool(config.get('enabled',False)),
                    'native_mode':self.native_active,
                    'native_preferred':bool(config.get('native_enabled',False)),
                    'dongle_present':present,'connected':connected and present,
                    'connected_ssid':session.get('ssid') if connected and present else None,
                    'connected_band':session.get('band') if connected and present else None}
            if action=='scan':
                if self.native_active:
                    return {'ok':False,'message':'Use o menu Wi-Fi do macOS no modo nativo.'}
                if not config.get('enabled',False):
                    return {'ok':False,'message':'Ligue o Wi-Fi para buscar redes.'}
                if self.wifi:
                    if self.wifi.active_vif is not None:
                        # Off-channel firmware scanning has left this dongle's
                        # USB control endpoint timed out. Keep the live link.
                        return {'ok':True,'scan_deferred':True}
                    # An automatic scan/association is already in progress.
                    # Interrupting it here used to restart the whole process.
                    return {'ok':True}
                self.wake.set();return {'ok':True}
            if action=='power' and isinstance(value.get('enabled'),bool):
                if bool(config.get('enabled',False))==value['enabled']:
                    return {'ok':True}
                config['enabled']=value['enabled'];self.save(config)
                # This switch controls only the legacy AIC fallback. macOS
                # owns the native radio power, even when the app is turned off.
                if not self.native_active:self.interrupt()
                return {'ok':True}
            if action=='forget':
                if self.native_active:
                    return {'ok':False,'message':'Gerencie redes salvas nos Ajustes do macOS.'}
                ssid=value.get('ssid')
                if not isinstance(ssid,str) or not 1<=len(ssid.encode('utf-8'))<=32:
                    return {'ok':False,'message':'Rede inválida.'}
                result=subprocess.run([str(HERE/'aic-wifi-credential'),'--delete',ssid],
                    stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=15)
                if result.returncode:
                    return {'ok':False,'message':'Não foi possível esquecer a rede.'}
                if config.get('ssid')==ssid:
                    config.update(ssid='',enabled=False)
                    config.pop('preferred_band',None)
                    self.save(config);self.interrupt()
                report_path=HERE/'redes-disponiveis.json'
                try:
                    report=json.loads(report_path.read_text())
                    for network in report.get('networks',[]):
                        if network.get('ssid')==ssid:network['known']=False
                    if report.get('configured_ssid')==ssid:
                        report.update(configured_ssid='',configured_band=None)
                    write_report(report_path,report,mode=0o644)
                except (OSError,ValueError):pass
                return {'ok':True}
            if action=='select':
                if self.native_active:
                    return {'ok':False,'message':'Use o menu Wi-Fi do macOS no modo nativo.'}
                ssid=value.get('ssid','');band=value.get('band');raw=ssid.encode('utf-8')
                if not 1<=len(raw)<=32 or band not in (0,1):
                    return {'ok':False,'message':'Rede inválida.'}
                supplied=value.get('pmk')
                if supplied is None:
                    try:credential(ssid)
                    except RuntimeError:return {'ok':False,'needs_password':True}
                else:
                    try:key=bytes.fromhex(supplied)
                    except (TypeError,ValueError):key=b''
                    if len(key)!=32:return {'ok':False,'message':'Senha inválida.'}
                    store_credential(ssid,key);key=None
                config.update(ssid=ssid,preferred_band=band,enabled=True,
                    credential='System Keychain')
                self.save(config);self.interrupt();return {'ok':True}
        return {'ok':False,'message':'Comando inválido.'}

    def serve_connection(self,connection):
        connection.settimeout(3);data=b''
        while b'\n' not in data and len(data)<4096:
            block=connection.recv(1024)
            if not block:break
            data+=block
        try:
            value=json.loads(data.split(b'\n',1)[0])
            if not isinstance(value,dict):raise ValueError()
            response=self.handle(value)
        except (OSError,ValueError,UnicodeError,RuntimeError,subprocess.TimeoutExpired) as error:
            response={'ok':False,'message':str(error) or 'Pedido inválido.'}
        connection.sendall(json.dumps(response).encode()+b'\n')

    def run(self):
        try:
            if SOCKET.exists() or SOCKET.is_symlink():
                info=SOCKET.lstat()
                if not stat.S_ISSOCK(info.st_mode):
                    raise RuntimeError('Caminho de controle AIC inválido.')
                SOCKET.unlink()
            listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.listener=listener
            listener.bind(str(SOCKET))
            os.chown(SOCKET,os.stat('/dev/console').st_uid,-1);os.chmod(SOCKET,0o600)
            listener.listen(4);listener.settimeout(.5)
            while not stop.is_set():
                try:connection,_=listener.accept()
                except socket.timeout:continue
                with connection:self.serve_connection(connection)
        finally:
            if self.listener:self.listener.close()
            try:SOCKET.unlink()
            except OSError:pass

    def start(self):
        self.thread=threading.Thread(target=self.run,name='AIC menu control',daemon=True)
        self.thread.start()
        self.native_thread=threading.Thread(target=self.monitor_native_power,
                                            name='AIC native power control',daemon=True)
        self.native_thread.start()

    def monitor_native_power(self):
        bridge=None;last_sequence=None
        try:
            while not stop.is_set():
                # NativeScanSession owns this user client in native mode.
                # A second reader could consume its power/leave commands.
                if self.config().get('native_enabled',False):
                    if bridge:bridge.close();bridge=None
                    last_sequence=None
                    stop.wait(.2);continue
                if bridge is None:
                    bridge=optional_radio_bridge()
                    last_sequence=None
                    if bridge is None:
                        stop.wait(3);continue
                try:
                    last_sequence=apply_native_power_command(self,bridge,last_sequence)
                    stop.wait(.2)
                except (OSError,RuntimeError,ValueError) as error:
                    print('AIC: controle nativo indisponível: '+str(error),flush=True)
                    bridge.close();bridge=None
                    stop.wait(3)
        finally:
            if bridge:bridge.close()

    def close(self):
        self.interrupt()
        if self.thread:self.thread.join(2)
        if self.native_thread:self.native_thread.join(2)

def main():
    if os.geteuid()!=0:raise RuntimeError('O serviço AIC exige root.')
    controller=Controller()
    def finish(*_):stop.set();controller.interrupt()
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,finish)
    controller.start()
    try:
        while not stop.is_set():
            # A request received during this iteration stays set until the
            # next one. Never clear it just before waiting for selection.
            controller.wake.clear()
            w=None;key=None;radio_bridge=None;session_stop=threading.Event();controller.session_stop=session_stop
            try:
                config=controller.config()
                if not config.get('enabled',False) and not config.get('native_enabled',False):
                    controller.wake.wait(3);continue
                if not controller.dongle_present():
                    controller.wake.wait(2);continue
                if run_native_session_if_available(config,session_stop,
                        on_mode_change=controller.set_native_active):continue
                if config.get('native_enabled',False) and recover_stuck_native_usb():
                    continue
                if config.get('native_enabled',False):
                    # Native mode is exclusive. A failed bridge must never
                    # silently create a legacy UTUN connection.
                    controller.wake.wait(3)
                    continue
                if session_stop.is_set():
                    session_stop=threading.Event()
                    controller.session_stop=session_stop
                if not config.get('enabled',False):
                    controller.wake.wait(3);continue
                ssid=config.get('ssid','')
                if not ssid:
                    # Fresh install: expose nearby WPA2 networks before any
                    # credential exists, then sleep until selection/rescan.
                    w=Wifi();w.native_stop=session_stop;controller.wifi=w
                    radio_bridge=optional_radio_bridge()
                    if radio_bridge:w.radio_observer=radio_bridge.safe_publish
                    publish_capabilities(w.identity())
                    print('AIC: primeira configuração; buscando redes disponíveis.',flush=True)
                    w.scan()
                    controller.wifi=None
                    w.close();w=None
                    controller.wake.wait()
                    continue
                key=credential(ssid)
                w=Wifi();w.native_stop=session_stop;w.target_band=config.get('preferred_band')
                radio_bridge=optional_radio_bridge()
                if radio_bridge:w.radio_observer=radio_bridge.safe_publish
                controller.wifi=w
                publish_capabilities(w.identity())
                w.native_connect=True
                print('AIC: conectando automaticamente a '+ssid,flush=True)
                w.scan(ssid,key)
            except KeyboardInterrupt:
                if stop.is_set():break
                print('AIC: sessão atualizada pelo menu.',flush=True)
            except (RuntimeError,ValueError,OSError,subprocess.TimeoutExpired) as error:
                print('AIC: '+str(error),flush=True)
            finally:
                key=None;controller.session_stop=None;controller.wifi=None
                if w:
                    mac=getattr(w,'mac',None)
                    if radio_bridge and mac:radio_bridge.safe_publish(False,None,mac)
                    try:w.close()
                    except OSError:pass
                if radio_bridge:radio_bridge.close()
            if not stop.is_set() and not session_stop.is_set():
                controller.wake.wait(3)
    finally:controller.close()

if __name__=='__main__':main()
