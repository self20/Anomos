'''
@author: John Schanck, Rich Jones
@license: see License.txt
'''

from Anomos.Connecter import AnomosFwdLink
from Anomos import BTFailure, INFO, WARNING, ERROR, CRITICAL

class Neighbor:
    def __init__(self, id, loc, ssls):
        self.id = id
        self.loc = loc
        self.ssl_session = ssls
        self.connection = None
    def set_connection(self, con):
        self.connection = con

class NeighborManager:
    '''NeighborManager keeps track of the neighbors a peer is connected to
    and which tracker those neighbors are on.
    '''
    def __init__(self, rawserver, config, certificate, logfunc):
        self.rawserver = rawserver
        self.config = config
        self.cert = certificate
        self.logfunc = logfunc
        self.neighbors = {}
        self.connections = {}
        self.incomplete = {}

        self.port = None
        self.waiting_tcs = {}

        self.failedPeers = []

    def failed_connections(self):
        return self.failedPeers

    def get_location(self, nid):
        nbr = self.neighbors.get(nid, None)
        if nbr:
            return nbr.loc
        return None

    def get_ssl_session(self, nid):
        nbr = self.neighbors.get(nid, None)
        if nbr:
            return nbr.ssl_session
        return None

    def add_neighbor(self, id, location, ssls):
        self.logfunc(INFO, "Adding Neighbor: (\\x%02x, %s)"
                                % (ord(id), location))
        self.neighbors[id] = Neighbor(id, location, ssls)

    def rm_neighbor(self, nid):
        if nid in self.failedPeers:
            self.failedPeers.remove(nid)
        elif self.incomplete.has_key(nid):
            self.incomplete.pop(nid)
        if self.has_neighbor(nid):
            con = self.neighbors[nid].connection
            if con:
                del self.connections[con]
            self.neighbors.pop(nid)

    def has_neighbor(self, nid):
        #TODO: Make this tracker specific.
        return self.neighbors.has_key(nid)

    def has_loc(self, loc):
        return loc in [n.loc for n in self.neighbors.values()]

    def is_incomplete(self, nid):
        #TODO: Make this tracker specific.
        return self.incomplete.has_key(nid)

    def count(self, tracker=None):
        #TODO: Make this tracker specific.
        return len(self.neighbors)

    def connection_completed(self, con):
        #TODO: Make this tracker specific.
        if not self.incomplete.has_key(con.id):
            # Completing a complete or non-existant connection...
            return
        del self.incomplete[con.id]
        self.neighbors[con.id].set_connection(con)
        for task in self.waiting_tcs.get(con.id, []):
            self.rawserver.add_task(task, 0) #TODO: add a min-wait time

    def connection_closed(self, con):
        self.rm_neighbor(con.id)

    def schedule_tc(self, sendfunc, id, tc, aeskey):
        '''Sometimes a tracking code is received before a neighbor is fully
        initialized. In those cases we schedule the TC to be sent once we get
        a "connection_completed" from the neighbor.'''
        def sendtc():
            sendfunc(id, tc, aeskey)
        self.waiting_tcs.setdefault(id,[])
        self.waiting_tcs[id].append(sendtc)

    def start_connection(self, loc, id):
        """
        @param loc: (IP, Port)
        @param id: The neighbor ID to assign to this connection
        @type loc: tuple
        @type id: int
        """
        if self.has_neighbor(id) or \
                self.incomplete.has_key(id) or \
                self.has_loc(loc):
            #Already had neighbor by that id or at that location
            #TODO: Resolve conflict
            return

        self.incomplete[id] = loc
        self.rawserver.start_ssl_connection(loc, handler=self)

    def sock_success(self, sock, loc):
        """
        @param sock: SingleSocket object for the newly created socket
        """
        for id,v in self.incomplete.iteritems():
            if v == loc:
                break
        else: return #loc wasn't found
        # Exchange the header and hold the connection open
        con = AnomosFwdLink(self, sock, id, established=False)
        self.connections[sock] = con
        self.add_neighbor(id, loc, sock.socket.get_session())

    def sock_fail(self, loc, err=None):
        #Remove nid,loc pair from incomplete
        for k,v in self.incomplete.items():
            if v == loc:
                self.failedPeers.append(k)
                del self.incomplete[k]
        #TODO: Do something with the error msg.

    def update_neighbor_list(self, list):
        freshids = dict([(i[2],(i[0],i[1])) for i in list])
        # Remove neighbors not found in freshids
        for id in self.neighbors.keys():
            if not freshids.has_key(id):
                self.rm_neighbor(id)
        # Start connections with the new neighbors
        for id,loc in freshids.iteritems():
            if not self.neighbors.has_key(id):
                self.start_connection(loc, id)
