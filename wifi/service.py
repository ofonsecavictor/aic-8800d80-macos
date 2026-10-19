#!/usr/bin/python3
"""LaunchDaemon and private local control socket for the AIC menu app."""
import json
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

HERE=Path(__file__).resolve().parent
SOCKET=Path('/private/tmp/aic-wifi-control.sock')
stop=threading.Event()

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

class Controller:
    def __init__(self):
        self.session_stop=None
        self.wake=threading.Event()
        self.lock=threading.Lock()
        self.listener=None
        self.thread=None
        self.presence_checked=0
        self.presence=False
        self.wifi=None

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
                    'dongle_present':present,'connected':connected and present,
                    'connected_ssid':session.get('ssid') if connected and present else None,
                    'connected_band':session.get('band') if connected and present else None}
            if action=='scan':
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
                config['enabled']=value['enabled'];self.save(config);self.interrupt()
                return {'ok':True}
            if action=='forget':
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
                    native_enabled=False,credential='System Keychain')
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

    def close(self):
        self.interrupt()
        if self.thread:self.thread.join(2)

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
            w=None;key=None;session_stop=threading.Event();controller.session_stop=session_stop
            try:
                config=controller.config()
                if not config.get('enabled',False):
                    controller.wake.wait(3);continue
                if not controller.dongle_present():
                    controller.wake.wait(2);continue
                ssid=config.get('ssid','')
                if not ssid:
                    # Fresh install: expose nearby WPA2 networks before any
                    # credential exists, then sleep until selection/rescan.
                    w=Wifi();w.native_stop=session_stop;controller.wifi=w
                    w.identity()
                    print('AIC: primeira configuração; buscando redes disponíveis.',flush=True)
                    w.scan()
                    controller.wifi=None
                    w.close();w=None
                    controller.wake.wait()
                    continue
                key=credential(ssid)
                w=Wifi();w.native_stop=session_stop;w.target_band=config.get('preferred_band')
                controller.wifi=w
                w.identity()
                from native_backend import Bridge,Manager,NativeError,NOT_FOUND
                try:bridge=Bridge() if config.get('native_enabled',False) else None
                except NativeError as error:
                    if error.status!=NOT_FOUND:raise
                    bridge=None
                if bridge:
                    print('AIC: controlador Wi-Fi nativo detectado.',flush=True)
                    Manager(w,bridge,session_stop,config,key).run();continue
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
                    try:w.close()
                    except OSError:pass
            if not stop.is_set() and not session_stop.is_set():
                controller.wake.wait(3)
    finally:controller.close()

if __name__=='__main__':main()
