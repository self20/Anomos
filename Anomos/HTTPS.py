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

import asynchat
import traceback

from Anomos import bttime, LOG as log
from M2Crypto import SSL
from cStringIO import StringIO
from gzip import GzipFile
from time import strftime


class HTTPSConnection(asynchat.async_chat):
    def __init__(self, socket, getfunc):
        asynchat.async_chat.__init__(self, socket)
        self.req = ''
        self.set_terminator('\n')
        self.getfunc = getfunc
        self.next_func = self.read_type

    ## HTTP handling methods ##
    def read_type(self, data):
        self.header = data.strip()
        words = data.split()
        if len(words) == 3:
            self.command, self.path, garbage = words
            self.pre1 = False
        elif len(words) == 2:
            self.command, self.path = words
            self.pre1 = True
            if self.command != 'GET':
                return None
        else:
            return None
        if self.command not in ('HEAD', 'GET'):
            return None
        self.headers = {}
        return self.read_header

    def read_header(self, data):
        data = data.strip()
        if data == '':
            # check for Accept-Encoding: header, pick a
            if self.headers.has_key('accept-encoding'):
                ae = self.headers['accept-encoding']
                log.debug("Got Accept-Encoding: " + ae + "\n")
            else:
                #identity assumed if no header
                ae = 'identity'
            # this eventually needs to support multple acceptable types
            # q-values and all that fancy HTTP crap
            # for now assume we're only communicating with our own client
            if ae.find('gzip') != -1:
                self.encoding = 'gzip'
            else:
                #default to identity.
                self.encoding = 'identity'
            r = self.getfunc(self, self.path, self.headers)
            if r is not None:
                self.answer(r)
                return None
        try:
            i = data.index(':')
        except ValueError:
            return None
        self.headers[data[:i].strip().lower()] = data[i+1:].strip()
        log.debug(data[:i].strip() + ": " + data[i+1:].strip())
        return self.read_header

    def answer(self, (responsecode, responsestring, headers, data)):
        if self.encoding == 'gzip':
            #transform data using gzip compression
            #this is nasty but i'm unsure of a better way at the moment
            compressed = StringIO()
            gz = GzipFile(fileobj = compressed, mode = 'wb', compresslevel = 9)
            gz.write(data)
            gz.close()
            compressed.seek(0,0)
            cdata = compressed.read()
            compressed.close()
            if len(cdata) >= len(data):
                self.encoding = 'identity'
            else:
                log.debug("Compressed: %i  Uncompressed: %i\n" % (len(cdata),len(data)))
                data = cdata
                headers['Content-Encoding'] = 'gzip'

        # i'm abusing the identd field here, but this should be ok
        if self.encoding == 'identity':
            ident = '-'
        else:
            ident = self.encoding
        username = '-'
        referer = self.headers.get('referer','-')
        useragent = self.headers.get('user-agent','-')
        timestamp = strftime("%d/%b/%Y:%H:%I:%S")
        log.info('%s %s %s [%s] "%s" %i %i "%s" "%s"' % (
                  self.socket.addr[0], ident, username, timestamp, self.header,
                  responsecode, len(data), referer, useragent))

        r = StringIO()
        r.write('HTTP/1.0 ' + str(responsecode) + ' ' + responsestring + '\r\n')
        if not self.pre1:
            headers['Content-Length'] = len(data)
            for key, value in headers.items():
                r.write(key + ': ' + str(value) + '\r\n')
            r.write('\r\n')
        if self.command != 'HEAD':
            r.write(data)

        self.push(r.getvalue())
        self.close_when_done()

    ## asynchat.async_chat methods ##
    def collect_incoming_data(self, data):
        self.req += data

    def found_terminator(self):
        creq = self.req
        self.req = ''
        self.next_func = self.next_func(creq)

    ## asyncore.dispatcher methods ##
    def handle_write(self):
        try:
            self.initiate_send()
        except SSL.SSLError, err:
            log.error(err)
            self.handle_error()

    def handle_read(self):
        try:
            asynchat.async_chat.handle_read(self)
        except SSL.SSLError, err:
            log.error(err)
            if "unexpected eof" not in errstr:
                #log.warning("SSLError: " + str(errstr))
                self.handle_error()

    def handle_expt(self):
        #TODO: Better logging here..
        traceback.print_exc()
        self.close()
    def handle_error(self):
        #TODO: Better logging here..
        traceback.print_exc()
        self.close()


class HTTPSServer(SSL.ssl_dispatcher):
    def __init__(self, addr, port, ssl_context, getfunc):
        SSL.ssl_dispatcher.__init__(self)
        self.create_socket(ssl_context)
        self.socket.setblocking(0)
        self.set_reuse_addr()
        self.bind((addr, port))
        self.listen(10) # TODO: Make this queue length a configuration option
                        # or determine a best value for it
        self.socket.set_post_connection_check_callback(lambda x,y: x != None)
        self.getfunc = getfunc

    def handle_accept(self):
        try:
            sock, addr = self.socket.accept()
        except SSL.SSLError, err:
            if "unexpected eof" not in err:
                self.handle_error()
            return
        except SSL.Checker.SSLVerificationError, err:
            log.info(err)
            return
        #if (self.ssl_ctx.get_verify_mode() is SSL.verify_none) or sock.verify_ok():
        conn = HTTPSConnection(sock, self.getfunc)
        #else:
        #    print 'client verification failed'
        #    sock.close()

    #def handle_connect(self):
    #    pass

    def handle_error(self):
        log.critical('\n'+traceback.format_exc())
        self.close()

    def handle_expt(self):
        log.critical('\n'+traceback.format_exc())
        self.close()

    def writable(self):
        return 0

