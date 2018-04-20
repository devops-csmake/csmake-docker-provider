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

    def _startListening(self):
        fulldockerd = subprocess.check_output(
            ['which', 'dockerd'] )
        prefix = ''
        if self.options['chroot'] is not None:
            prefix = self.options['chroot'] + '/'
        #Is the host a remote or local?
        if not self.options['host'].startswith('unix://'):
            portAddress = self.options['port'].address()
            hostaddress = 'tcp://%s:%d' % portAddress
            self.host = address
            self.local = False
        else:
            hostaddress = 'unix://%s%s' % (prefix, self.options['host'][7:])
            self.host = self.options['host']
            self.local = True

        #TODO: Sanity check....is there already a dockerd or pid file live?
        bridge = []
        if 'bridge' in self.options:
            bridge = ['--bridge', self.options['bridge']]

        command = [
          'sudo', fulldockerd.strip() ] + bridge + [
          '--exec-root', prefix + self.options['exec-root'],
          '--graph', prefix + self.options['graph'],
          '--host', hostaddress,
          '--pidfile', prefix + self.options['pidfile']
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
                command )
            if self.process.poll() is not None:
                raise Exception("Process is not running")
            if 'DOCKER_HOST' in os.environ:
                self.oldhost = os.environ['DOCKER_HOST']
            os.environ['DOCKER_HOST'] = self.host
            address = port.address()
            #Wait for 5 seconds to see the process come about
            for x in range(0,50):
                try:
                    subprocess.check_call(
                        ['docker', '-H', hostaddress, 'info'] )
                    #Process is listening - probably
                    if self.process.poll() is not None:
                        raise Exception("Process is not running")
                    break
                except:
                    #Process is not listening yet wait .1 sec and try again
                    time.sleep(.1)
                    if self.process.poll() is not None:
                        raise Exception("Process is not running")
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
                processes = processes.split()
                for process in processes:
                    self.configManager.shellout(
                        subprocess.call,
                        [ 'kill', '-9', process ] )
            except:
                self.log.exception("Could not stop dockerd using standard procedure, attempting to use sudo calls exclusively")
                if self.process is None:
                    raise Exception("dockerd service never started")
                subprocess.call("""set -eux
                    for x in `sudo ps -o pid --ppid %d --noheaders`
                    do
                        sudo kill -9 $x
                    done
                    """ % self.process.pid,
                    shell=True,
                    stdout=self.log.out(),
                    stderr=self.log.err() )
                subprocess.call(
                    ['sudo', 'kill', str(self.process.pid)],
                    stdout=self.log.out(),
                    stderr=self.log.err())
        except:
            self.log.exception("Couldn't terminate process cleanly")

        finally:
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
