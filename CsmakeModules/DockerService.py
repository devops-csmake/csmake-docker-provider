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
from Csmake.CsmakeAspect import CsmakeAspect
from CsmakeDockerProvider.DockerServiceProvider import DockerServiceProvider

class DockerService(CsmakeAspect):
    """Purpose: Provide a running instance of dockerd that can be used
                in a build setting specific to a chrooted environment
                or other specific use to separate it from the build system's
                dockerd instance
                NOTE: If chroot is specified, the docker container will
                      execute in the chroot context, but the dockerd process
                      will run in the build system's environment, i.e.,
                      docker must be installed on the build system for
                      this module to work...and, of course, this may
                      cause some inconsistencies if the versions of docker
                      are wildly different between a build target image
                      and the build system's version of docker.
                      If this is important - a second docker faux service
                      would need to be created to start the docker daemon
                      from the chroot environment (which is a whole other
                      can of worms....not covered in this implementation)
                TODO: Use as a safeguard for ensuring a dockerd is running
                      for the build - it currently doesn't check to see
                      if what is specified (the default options, for example
                      which is, if there is no chroot, is where the default
                      dockerd will run on the build system)
     Type: Module or Aspect   Library: csmake-docker-provider
     Options:
         bridge - (OPTIONAL) Any containers created in this instance will
                             be attached to the given bridge, which
                             will not be set up automatically by dockerd
                             see: https://docs.docker.com/network/bridge/
                  Default: docker0 (the docker default)
         exec-root - (OPTIONAL) Root location of the Docker execdriver
                      in a chroot, this may require docker to be installed
                      in the chroot - may be problematic to use the default
                      for reasons listed above, in this case.
                  Default: chroot + /var/run/docker
         graph - (OPTIONAL) Root of the docker runtime store
                  Default: chroot + /var/lib/docker
         host - (OPTIONAL) Specifies the way to contact dockerd
                  NOTE: This breaks from the way dockerd would take the
                    parameter, because you must use the interfaces and port
                    parameters if you want to have the docker instance available
                    on the network.  In this case, just specify:
                      tcp:// 
                    and use interfaces and port to define the networking aspects
                  NOTE: To specify local, still use unix://<path>
                    and in a chroot environment, dockerd will be setup
                    in the chroot's version of the path specified in <path>
                    and (as below) DOCKER_HOST will not have the chroot
                    in the path (it's assumed that you'll be running the
                    client in the chroot).  If this is a problem,
                    you'll need to specialize this module, or use -H
                    when running docker to override DOCKER_HOST.
                  Default: unix://chroot + /var/run/docker.sock
         pidfile - (OPTIONAL) The location for dockerd to put the pidfile
                  Default: chroot + /var/run/docker.pid
         storage-driver - (OPTIONAL) The storage driver to use:
                           e.g., devicemapper, aufs, etc...
                  Default: devicemapper
         interfaces - (OPTIONAL) List of interfaces to listen on,
                        delimited with commas or newlines.
                        When "host" doesn't start with unix://
                      Default: localhost
         tag - (OPTIONAL) allows for several dockerd services to be
                          operational at the same time in the same build
                          given unique values for 'tag'
                      Default: <nothing>
         chroot - (OPTIONAL) Will operate the dockerd in a chrooted environment
                          determined by the path provided
                    Default: /
         port - (OPTIONAL) Will stand up the dockerd on the given port
                    when the "host" option isn't a unix:// local listener
                 Default: a currently open port in 'port-range'
         port-range - (OPTIONAL) Will stand up the dockerd in a given range
                   Ignored if a specific port is called out by 'port'
                   when the "host" option isn't a unix:// local listener
                   Format:  <lower> - <upper> (Inclusive)
                   Default: 2222-3333
         (NOTE: no-sudo if specified, will not be honored for this module)
     Phases/JoinPoints:  
         build - will stand the service up in the build phase
                 When used as a regular section, StopDockerService must be used
         start__build - will stand up the service at the start of the
                        decorated regular section
         end__build - will tear down the service at the end of the section
     Environment:
         The shell environment will be modified for the DOCKER_HOST variable
         so that clients in the build while DockerService is active will
         automagically use the right dockerd....however....
         - if you use multiple instances of the DockerService module with
           tags, you'll need to manually set -H for the docker clients
           because there's only one DOCKER_HOST variable in the shell...
           Results if you interleave the lifecycles of the DockerService
           for DOCKER_HOST will be indeterminate.
           Multiple csmake instances that all use DockerService modules
           will be safe as long as their shell environments are segregated.
    """

    def _startService(self, options):
        if DockerServiceProvider.hasServiceProvider(self.tag):
            self.log.error("dockerd with service tag '%s' already executing", self.tag)
            self.log.failed()
            self._unregisterOnExitCallback("_stopService")
            return None

        self.provider = DockerServiceProvider.createServiceProvider(
            self.tag,
            self,
            **options)
        self.provider.startService()
        if self.provider is not None and self.provider.isServiceExecuting():
            self.log.passed()
        else:
            self.log.error("The dockerd service could not be started")
            self.log.failed()
            self._unregisterOnExitCallback("_stopService")
        return None

    def _stopService(self):
        DockerServiceProvider.disposeServiceProvider(self.tag)
        self._unregisterOnExitCallback("_stopService")
        self.log.passed()

    def build(self, options):
        self.tag = '_'
        if 'tag' in options:
            self.tag = options['tag']
            del options['tag']
        self._dontValidateFiles()
        self._registerOnExitCallback("_stopService")
        self.log.passed()
        return self._startService(options)

    def start__build(self, phase, options, step, stepoptions):
        return self.build(options)

    def end__build(self, phase, options, step, stepoptions):
        self._stopService()
