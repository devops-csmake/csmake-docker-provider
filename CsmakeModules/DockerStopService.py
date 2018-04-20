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
from CsmakeDockerProvider.DockerServiceProvider import DockerServiceProvider
from Csmake.CsmakeAspect import CsmakeAspect

class DockerStopService(CsmakeAspect):
    """Purpose: End execution of a DockerService section
                May be used as an aspect on a section that would
                    need the service ended
       Type: Module   Library: csmake-docker-provider
       Options:
           tag - (OPTIONAL) Must match the tag given to DockerService that
                   this section is ending
       Phases/JoinPoints:
           build - end execution of DockerService
           end__build - end execution of DockerService at the conclusion of the
                        decorated regular section"""

    def _stopService(self, tag):
        try:
            self._unregisterOtherClassOnExitCallback(
                "DockerService",
                "_stopService" )
        except:
            pass
        DockerServiceProvider.disposeServiceProvider(tag)

    def build(self, options):
        tag = ''
        if 'tag' in options:
            tag = options['tag']
        self._stopService()
        self.log.passed()
        return None

    def end__build(self, phase, options, step, stepoptions):
        return self.build(options)

