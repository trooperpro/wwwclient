#!/usr/bin/env python
# Encoding: iso-8859-1
# vim: tw=80 ts=4 sw=4 noet
# -----------------------------------------------------------------------------
# Project   : WWWClient - Python client Web toolkit
# -----------------------------------------------------------------------------
# Author    : Sebastien Pierre <sebastien@xprima.com>
# Creation  : 19-Jun-2006
# Last mod  : 20-Jun-2006
# -----------------------------------------------------------------------------

# TODO: Allow Request to have parameters in body or url and attachments as well

import urlparse, urllib, mimetypes, re
import curl

__version__ = "2.0"

HTTP               = "http"
HTTPS              = "https"
PROTOCOLS          = (HTTP, HTTPS)

GET                = "GET"
POST               = "POST"
HEAD               = "HEAD"
METHODS            = (GET, POST, HEAD)

FILE_ATTACHMENT    = curl.FILE_ATTACHMENT
CONTENT_ATTACHMENT = curl.CONTENT_ATTACHMENT

# -----------------------------------------------------------------------------
#
# PARAMETERS
#
# -----------------------------------------------------------------------------

class Pairs:
	"""Pairs are list of pairs (name,values) quite similar to
	dictionaries, excepted that there can be multiple values for a single key,
	and that the order of the keys is preserved. They can be easily converted to
	URL parameters, headers and cookies."""

	def __init__( self, params=None ):
		self.pairs = []
		self.merge(params)

	def set( self, name, value=None ):
		"""Sets the given name to hold the given value. Every previous value set
		or added to the given name will be cleared."""
		self.clear(name)
		self.add(name, value)
	
	def get( self, name ):
		"""Gets the pair with the given name (case-insensitive)"""
		for key, value in self.pairs:
			if name.lower().strip() == key.lower().strip():
				return value
		return None
	
	def add( self, name, value=None ):
		"""Adds the given value to the given name. This does not destroy what
		already existed."""
		pair = (name,value)
		if pair not in self.pairs: self.pairs.append((name, value))
	
	def clear( self, name ):
		"""Clears all the (name,values) pairs which have the given name."""
		self.pairs = filter(lambda x:x[0]!= name, self.pairs)

	def merge( self, parameters ):
		"""Merges the given parameters into this parameters list."""
		if parameters == None: return
		if type(parameters) == dict:
			for name, value in parameters.items():
				self.add(name, value)
		elif type(parameters) in (tuple, list):
			for name, value in parameters:
				self.add(name, value)
		else:
			for name, value in parameters.pairs:
				self.add(name, value)

	def asURL( self ):
		"""Returns an URL-encoded version of this parameters list."""
		return urllib.urlencode(self.pairs)
	
	def asFormData( self ):
		"""Returns an URL-encoded version of this parameters list."""
		return urllib.urlencode(self.pairs)

	def asHeaders( self ):
		"""Returns a list of header strings."""
		return list("%s: %s" % (k,v) for k,v in self.pairs)

	def asCookies( self ):
		"""Returns these pairs as cookies"""
		return "; ".join("%s=%s" % (k,v) for k,v in self.pairs)

	def __repr__(self):
		return repr(self.pairs)

# -----------------------------------------------------------------------------
#
# HTTP REQUEST WRAPPER
#
# -----------------------------------------------------------------------------

class Request:
	"""The Request object encapsulates an HTTP request so that it is easy to
	specify headers, cookies, data and attachments."""

	def __init__( self, method=GET, url="/", params=None, data=None ):
		self._method     = method.upper()
		self._url        = url
		self._params      = Pairs(params)
		self._cookies     = Pairs()
		self._headers    = Pairs()
		self._data       = data
		self._attachments = []
		# Ensures that the method is a proper one
		if self._method not in METHODS:
			raise Exception("Method not supported: %s" % (method))

	def method( self ):
		"""Returns the method for this request"""
		return self._method

	def url( self ):
		"""Returns this request url"""
		if self._params.pairs:
			if self._method == POST and self._data != None or self._attachments:
				return self._url
			else:
				return self._url + "?" + self._params.asURL()
		else:
			return self._url

	def params( self ):
		return self._params
	
	def cookies( self ):
		return self._cookies

	def header( self, name, value=curl ):
		"""Gets or set the given header."""
		if value == curl:
			return self._headers.get(name)
		else:
			self._headers.set(name, str(value))

	def headers( self ):
		"""Returns the headers for this request as a Pairs instance."""
		headers = Pairs(self._headers)
		# Takes care of cookies
		if self._cookies.pairs:
			cookie_header = headers.get("Cookie")
			if cookie_header:
				headers.set("Cookie", cookie_header + "; " + self._cookies.asCookies())
			else:
				headers.set("Cookie", self._cookies.asCookies())
		return headers

	def data( self, data=curl ):
		"""Sets the urlencoded data for this request. The request will be
		automatically turned into a post."""
		assert not self._attachments, "Request already has attachments"
		if data == curl:
			return self._data
		else:
			self._method = POST
			self._data   = data

	def attach( self, name, file=None, content=None ):
		"""Attach the given file or content to the request. This will turn the
		request into a post"""
		assert self._data == None, "Request already has data"
		self._method = POST
		if file != None:
			self._attachments.append((name, file, FILE_ATTACHMENT))
		elif content != None:
			self._attachments.append((name, file, CONTENT_ATTACHMENT))
		else:
			raise Exception("Expected file or content")

	def attachments( self ):
		return self._attachments

# -----------------------------------------------------------------------------
#
# TRANSACTION
#
# -----------------------------------------------------------------------------

class Transaction:
	"""A transaction encaspulates a request and its responses.
	
	Attributes::

		@session			Enclosing session
		@request			Initiating request
		@data				Response data
		@cookies			Response cookies
		@redirect			Transaction for the redirection (None by default)
		@done				Tells if the transaction was executed or not
	
	"""

	def __init__( self, session, request ):
		self._curl     = session._httpClient
		self._curl.verbose = session.verbose
		self._session  = session
		self._request  = request
		self._cookies  = Pairs()
		self._done     = False
	
	def session( self ):
		"""Returns this transaction session"""
		return self._session

	def request( self ):
		"""Returns this transaction request"""
		return self._request

	def cookies( self ):
		"""Returns this transaction cookies (including the new cookies, if the
		transaction is set to merge cookies)"""
		return self._cookies

	def data( self ):
		"""Returns the response data (implies that the transaction was
		previously done)"""
		return self._curl.data()

	def redirect( self ):
		"""Returns the URL to which the response redirected, if any."""
		return self._curl.redirect()

	def url( self ):
		"""Returns the requested URL."""
		return self.request().url()
	
	def newCookies( self ):
		"""Returns the list of new cookies."""
		return Pairs(self._curl.newCookies())

	def do( self ):
		"""Executes this transaction"""
		# We do not do a transaction twice
		if self._done: return
		# We prepare the headers
		request  = self.request()
		headers  = request.headers() 
		# We merge the session cookies into the request
		request.cookies().merge(self.session().cookies())
		# As well as this transaction cookies
		request.cookies().merge(self.cookies())
		# We send the request as a GET
		if request.method() == GET:
			self._curl.GET(
				request.url(),
				headers=request.headers().asHeaders()
			)
		# Or as a POST
		elif request.method() == POST:
			self._curl.POST(
				request.url(),
				data=request.data(),
				attach=request.attachments(),
				headers=request.headers().asHeaders()
			)
		# The method may be unsupported
		else:
			raise Exception("Unsupported method:", request.method())
		# We merge the new cookies if necessary
		self._done = True
		return self
	
	def done( self ):
		return self._done

# -----------------------------------------------------------------------------
#
# SESSION
#
# -----------------------------------------------------------------------------

class SessionException(Exception): pass
class Session:
	"""A Session encapsulates a number of transactions (couples of request and
	responses). The session stores common state (the cookies), that is shared by
	the different transactions. Each session has a maximum number of transaction
	which is given by its @maxTransactions attribute.

	Attributes::

		@host				Session host (by name or IP)
		@protocol			Session protocol (either HTTP or HTTPS)
		@transactions		List of transactions
		@maxTransactions	Maximum number of transactions in registered in
							this session
		@cookies			List of cookies for this session
		@userAgent			String for this user session agent

	"""

	MAX_TRANSACTIONS = 10

	def __init__( self, url=None, verbose=False ):
		"""Creates a new session at the given host, and for the given
		protocol."""
		self._httpClient      = curl.HTTPClient()
		self._host            = None
		self._protocol        = None
		self._transactions    = []
		self._cookies         = Pairs()
		self._userAgent       = "Mozilla/5.0 (X11; U; Linux i686; fr; rv:1.8.0.4) Gecko/20060608 Ubuntu/dapper-security"
		self._maxTransactions = self.MAX_TRANSACTIONS
		self.verbose          = verbose
		self.MERGE_COOKIES    = True
		if url: self.get(url)

	def cookies( self ):
		return self._cookies

	def last( self ):
		"""Returns the last transaction of the session, or None if there is not
		transaction in the session."""
		if not self._transactions: return None
		return self._transactions[-1]
	
	def referer( self ):
		if not self.last(): return None
		else: return self.last().url()

	def get( self, url="/", params=None, follow=True, do=True ):
		url         = self.__processURL(url)
		request     = self._createRequest( url=url, params=params )
		transaction = Transaction( self, request )
		self.__addTransaction(transaction)
		# We do the transaction
		if do:
			transaction.do()
			if self.MERGE_COOKIES: self._cookies.merge(transaction.newCookies())
			# And follow the redirect if any
			while transaction.redirect() and follow:
				transaction = self.get(transaction.redirect(), do=True)
		return transaction

	def post( self, url=None, params=None, data=None, follow=True, do=True ):
		url = self.__processURL(url)
		request     = self._createRequest(
			method=POST, url=url, params=params, data=data
		)
		transaction = Transaction( self, request )
		self.__addTransaction(transaction)
		if do:
			transaction.do()
			if self.MERGE_COOKIES: self._cookies.merge(transaction.newCookies())
			# And follow the redirect if any
			while transaction.redirect() and follow:
				transaction = self.get(transaction.redirect(), do=True)
		return transaction
	
	def submit( self, form, values={}, action=None,  method=POST, do=True ):
		"""Submits the given form with the current values and action (first
		action by default) to the form action url, and doing
		a POST or GET with the resulting values (POST by default).

		The submit method is a convenience wrapper that processes the given form
		and gives its values as parameters to the post method."""
		# We fill the form values
		# And we submit the form
		url            = form.action or self.referer()
		url_parameters = form.submit(action, **values)
		if method == POST:
			return self.post( url, data=urllib.urlencode(url_parameters), do=do )
		elif method == GET:
			return self.get( url, params=url_parameters, do=do )
		else:
			raise SessionException("Unsupported method for submit: " + method)

	def __processURL( self, url ):
		"""Processes the given URL, by storing the host and protocol, and
		returning a normalized, absolute URL"""
		old_url = url
		if url == None and not self._transactions: url = "/"
		if url == None and self._transactions: url = self.last().request.url()
		# If we have no default host, then we ensure that there is an http
		# prefix (for instance, www.google.com could be mistakenly interpreted
		# as a path)
		if self._host == None:
			if not url.startswith("http"): url = "http://" + url
		# And now we parse the url and update the session attributes
		protocol, host, path, parameters, query, fragment =  urlparse.urlparse(url)
		if   protocol == "http": self._protocol  = HTTP
		elif protocol == "https": self._protocol = HTTPS
		if host: self._host =  host
		# We recompose the url
		assert not path.startswith("ppg.h")
		url = "%s://%s" % (self._protocol, self._host)
		if   path and path[0] == "/": url += path
		elif path:      url += "/" + path
		else:           url += "/"
		if parameters:  url += ";" + parameters
		if query:       url += "?" + query
		if fragment:    url += "#" + fragment
		return url

	def _createRequest( self, **kwargs ):
		request = Request(**kwargs)
		last    = self.last()
		if last: request.header("Referer", self.referer())
		return request

	def __addTransaction( self, transaction ):
		"""Adds a transaction to this session."""
		if len(self._transactions) > self._maxTransactions:
			self._transactions = self._transactions[1:]
		self._transactions.append(transaction)

# Events
# - Redirect
# - New cookie
# - Success
# - Error
# - Timeout
# - Exception

# EOF
