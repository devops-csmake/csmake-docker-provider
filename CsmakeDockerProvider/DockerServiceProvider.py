# <copyright>
# (c) Copyright 2018 Cardinal Peak Technologies
# (c) Copyright 2017 Hewlett Packard Enterprise Development LP
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
# </copyright>
import threading
import subprocess
import os.path
import time
from CsmakeProviders.CsmakeServiceProvider import CsmakeServiceProvider
from CsmakeProviders.CsmakeServiceProvider import CsmakeServiceDaemon

class DockerServiceDaemon(CsmakeServiceDaemon):
    def __init__(self, module, provider, options):
        CsmakeServiceDaemon.__init__(self, module, provider, options)
        self.process = None
        self.oldhost = None
        self.host = None
        self.bindMounts = []

    def _umountBinds(self):
        for real, bind in self.bindMounts:
            try:
                subprocess.call(['sudo', 'umount', '-l', bind])
            except:
                self.log.info("umount docker short exec path failed: %s", bind)
            try:
                subprocess.call(['sudo', 'rmdir', '-p', bind])
            except:
                self.log.info("rmdir docker short exec path failed: %s", bind)

    def _startListening(self):
        tag = self.provider.tag
        fulldockerd = subprocess.check_output(
            ['which', 'dockerd'] )
        prefix = ''
        if self.options['chroot'] is not None:
            prefix = os.path.abspath(self.options['chroot'] + '/')

        #Setup all the paths.
        realExecPath = prefix + self.options['exec-root']
        #Is the length of the socket path to container socket
        # greater than 91 (Minimum known max path length for unix socket)
        if len(realExecPath) + len('/libcontainerd/docker-containerd.sock') > 91:
            #Yup, we have to do a bind mount.
            bindExecPath = os.path.join(
                os.path.expanduser('~'),
                '.cs-docker',
                tag )
            self.bindMounts.append((realExecPath, bindExecPath))
        else:
            bindExecPath = realExecPath

        #Is the host a remote or local?
        if not self.options['host'].startswith('unix://'):
            portAddress = self.options['port'].address()
            hostaddress = 'tcp://%s:%d' % portAddress
            self.host = hostaddress
            self.local = False
        else:
            hostaddress = 'unix://%s%s' % (prefix, self.options['host'][7:])
            self.host = self.options['host']
            self.local = True

        #TODO: Sanity check....is there already a dockerd or pid file live?
        bridge = []
        if 'bridge' in self.options:
            bridge = ['--bridge', self.options['bridge']]

        subprocess.check_call(['sudo', 'mkdir', '-p', os.path.join(
            realExecPath, "libcontainerd")])
        subprocess.check_call(['sudo', 'mkdir', '-p', prefix + self.options['graph']])
        subprocess.check_call(['sudo', 'mkdir', '-p', bindExecPath])
        try:
            for real, bind in self.bindMounts:
                subprocess.check_call(['sudo', 'mount', '--bind', real, bind])
        except:
            self._umountBinds()

        command = [
          'sudo', fulldockerd.strip() ] + bridge + [ '--debug',
          '--exec-root', bindExecPath,
          '--graph', prefix + self.options['graph'],
          '--host', hostaddress,
          '--pidfile', prefix + self.options['pidfile'],
          '--storage-driver', self.options['storage-driver']
        ]
        self.log.debug("Calling Popen with: %s", ' '.join(command))
        port = self.options['port']
        port.lock()
        port.unbind()
        try:
            #This ignores both chroot and no-sudo!
            #The process is running outside the chroot and
            #  will poke into the chroot
            self.process = subprocess.Popen(
                command, stdout=self.log.out(), stderr=self.log.err() )
            self.log.debug("Popen finished")
            self.log.out()
            if self.process.poll() is not None:
                raise Exception("Process is not running")
            if 'DOCKER_HOST' in os.environ:
                self.oldhost = os.environ['DOCKER_HOST']
            os.environ['DOCKER_HOST'] = self.host
            self.log.debug("DOCKER_HOST set")
            self.log.out()
            address = port.address()
            #Wait for 5 seconds to see the process come about
            for x in range(0,50):
                try:
                    self.log.debug("Testing dockerd openness")
                    self.log.out()
                    subprocess.check_call(
                        ['docker', '-H', hostaddress, 'info'],
                        stdout=self.log.out(),
                        stderr=self.log.err() )
                    #Process is listening - probably
                    if self.process.poll() is not None:
                        raise Exception("Process is not running")
                    break
                except:
                    #Process is not listening yet wait .1 sec and try again
                    self.log.debug("Not ready yet")
                    self.log.out()
                    time.sleep(.1)
                    self.log.debug("Polling again")
                    self.log.out()
                    if self.process.poll() is not None:
                        raise Exception("Process is not running")
                    self.log.debug("Poll completed")
                    self.log.out()
            else:
                if self.process.poll() is not None:
                    raise Exception("Process never started")
                else:
                    raise Exception("Process didn't listen after 5 seconds")
        finally:
            port.unlock()

    def _cleanup(self):
        try:
            try:
                if self.process is None:
                    raise Exception("dockerd service never started")
                processes = self.configManager.shellout(
                    subprocess.check_output,
                    [ 'ps', '-o', 'pid', '--ppid', str(self.process.pid), '--noheaders' ] )
                process = processes.split()[0] #There must only be one here
                subprocess.call(
                    [ 'sudo', 'kill', '-SIGTERM', process ],
                    stdout=self.log.out(),
                    stderr=self.log.err() )
                
                try:
                    for x in range(55):
                        subprocess.check_call(
                            [ 'ps', '-q', process, '--noheaders' ],
                            stdout=self.log.out(),
                            stderr=self.log.err() )
                        time.sleep(0.1)
                    subprocess.call(
                        ['sudo', 'kill', '-SIGKILL', process ],
                        stdout=self.log.out(),
                        stderr=self.log.err())
                    for x in range(25):
                        subprocess.check_call(
                            [ 'ps', '-q', process, '--noheaders' ],
                            stdout=self.log.out(),
                            stderr=self.log.err() )
                        time.sleep(0.1)
                    self.log.error("Could not terminate docker process: %d", self.process.pid)
                except:
                    self.log.info("Docker process terminated successfully")
            except:
                self.log.exception("Couldn't terminate process cleanly")

        finally:
            self._umountBinds()
            if self.oldhost is not None:
                os.environ['DOCKER_HOST'] = self.oldhost
            elif 'DOCKER_HOST' in os.environ:
                del os.environ['DOCKER_HOST']

class DockerServiceProvider(CsmakeServiceProvider):

    serviceProviders = {}

    def __init__(self, module, tag, **options):
        CsmakeServiceProvider.__init__(self, module, tag, **options)
        self.serviceClass = DockerServiceDaemon

    def _processOptions(self):
        CsmakeServiceProvider._processOptions(self)
        execRoot = '/var/run/docker'
        graph = '/var/lib/docker'
        host = 'unix:///var/run/docker.sock'
        pid = '/var/run/docker.pid'
        if 'exec-root' not in self.options:
            self.options['exec-root'] = execRoot
        if 'graph' not in self.options:
            self.options['graph'] = graph
        if 'host' not in self.options:
            self.options['host'] = host
        if 'pidfile' not in self.options:
            self.options['pidfile'] = pid
        if 'storage-driver' not in self.options:
            self.options['storage-driver'] = 'devicemapper'

