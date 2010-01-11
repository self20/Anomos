# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Written by John Schanck

from Anomos.AnomosNeighborInitializer import AnomosNeighborInitializer
from Anomos.P2PConnection import P2PConnection

from Anomos import LOG as log

class NatCheck(object):

    def __init__(self, ssl_ctx, resultfunc, peerid, ip, port):
        self.resultfunc = resultfunc
        self.peerid = peerid
        self.ip = ip
        self.port = port
        self.id = chr(255)

        self.socket = P2PConnection(addr=(ip,port), ssl_ctx=ssl_ctx)
        self.socket.set_post_connection_check_callback(lambda x,y: x != None)

        AnomosNeighborInitializer(self, self.socket, self.id)

    def initializer_failed(self, *args):
        self.answer(False)

    def connection_completed(self, *args):
        self.answer(True)

    def answer(self, result):
        self.resultfunc(self.peerid, result)
