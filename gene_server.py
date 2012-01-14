#!/usr/bin/python

"""
gene_server v0.01 

- a xmlrpc server providing a storage/query service for the GA trade system

Copyright 2011 Brian Monkaba

This file is part of ga-bitbot.

    ga-bitbot is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    ga-bitbot is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with ga-bitbot.  If not, see <http://www.gnu.org/licenses/>.
"""

# 
#   gene server
#	- a xmlrpc server providing a storage/query/configuration/monitoring service for the GA trade system
#

import gene_server_config
__server__ = gene_server_config.__server__
__port__ = gene_server_config.__port__
__path__ = "/gene"


import sys
import time
import json
from SimpleXMLRPCServer import SimpleXMLRPCServer
from SimpleXMLRPCServer import SimpleXMLRPCRequestHandler
from operator import itemgetter, attrgetter

quit = 0
MAX_PID_MESSAGE_BUFFER_SIZE = 255
AUTO_BACKUP_AFTER_N_SAVES = 60
max_len = 600
max_bobs = 1000

g_save_counter = 0
g_d = [[],[],[],[]]
g_trgt = json.dumps({'buy':0})

g_bobs = [[],[],[],[]]

g_pids = {}


def echo(msg):
	return msg

def put_target(target):
	global g_trgt
	g_trgt = target
	return "OK"

def get_target():
	global g_trgt
	return g_trgt

def get_gene(n_sec,quartile):
	global g_d
	global g_bobs

	t = time.time() - n_sec
	#get the highest score calculated within the last n seconds
	#or return the latest if none are found.
	r = []
	#collect the high scoring records
	for a_d in g_d[quartile - 1]:
		if a_d['time'] > t:
			r.append(a_d)

	#collect the bob records
	for a_d in g_bobs[quartile - 1]:
		if a_d['time'] > t:
			r.append(a_d)

	#print "searching for greater than",t 
	#print "found",len(r),"records"
	#if no record found, grab the most recent
	if len(r) == 0:
		r = sorted(g_d[quartile - 1], key=itemgetter('score'),reverse = True)[0]
		r.append(sorted(g_bobs[quartile - 1], key=itemgetter('score'),reverse = True)[0])
	
	if len(r) > 1:
		#if more than one record found find the highest scoring one
		r = sorted(r, key=itemgetter('score'),reverse = True)[0]

	print "get",r['time'],r['score']
		
	return json.dumps(r)

def get_all_genes(quartile):
	global g_d
	return json.dumps(sorted(g_d[quartile - 1], key=itemgetter('score')))

def get_bobs(quartile):
	global g_bobs
	return json.dumps(sorted(g_bobs[quartile - 1], key=itemgetter('score')))

def put_gene(d,quartile):
	global g_d
	global g_bobs
	#dictionary must have two key values, time & score
	#add the record and sort the dictionary list
	d = json.loads(d)

	if any(adict['gene'] == d['gene'] for adict in g_d[quartile - 1]):
		print "put_gene: duplicate gene detected"
		for i in xrange(len(g_d[quartile - 1])):
			if g_d[quartile - 1][i]['gene'] == d['gene']:
				print "put_gene: removing previous record"
				g_d[quartile - 1].pop(i)
				break

	#check the bob dict to see if the gene is already captured
	if any(adict['gene'] == d['gene'] for adict in g_bobs[quartile - 1]):
		print "put_gene: duplicate BOB gene detected"
		#update the gene
		put_bob(json.dumps(d),quartile)
		return "OK"
	
	#timestamp the gene submission
	d['time'] = time.time()

	g_d[quartile - 1].append(d)
	g_d[quartile - 1] = sorted(g_d[quartile - 1], key=itemgetter('score'),reverse = True)
	
	print "put",d['time'],d['score']
	#prune the dictionary list
	if len(g_d[quartile - 1]) > max_len:
		g_d[quartile - 1] = g_d[quartile - 1][:max_len]
	return "OK"

def put_bob(d,quartile):
	global g_bobs
	#dictionary must have two key values, time & score
	#add the record and sort the dictionary list
	d = json.loads(d)

	if any(adict['gene'] == d['gene'] for adict in g_bobs[quartile - 1]):
		print "put_bob: duplicate gene detected"
		for i in xrange(len(g_bobs[quartile - 1])):
			if g_bobs[quartile - 1][i]['gene'] == d['gene']:
				print "put_bob: removing previous record"
				g_bobs[quartile - 1].pop(i)
				break

	#timestamp the gene submission
	d['time'] = time.time()

	g_bobs[quartile - 1].append(d)
	g_bobs[quartile - 1] = sorted(g_bobs[quartile - 1], key=itemgetter('score'),reverse = True)
	
	print "put bob",d['time'],d['score']
	#prune the dictionary list
	if len(g_bobs[quartile - 1]) > max_bobs:
		g_bobs[quartile - 1] = g_bobs[quartile - 1][:max_bobs]
	return "OK"

### watchdog services ###
def pid_alive(pid):
	global g_pids
	#pid ping (watchdog reset)
	if pid in g_pids.keys(): #existing pid
		g_pids[pid]['watchdog_reset'] = time.time()
	else: #new pid
		g_pids.update({pid:{'watchdog_reset':time.time(),'msg_buffer':''}})
	return "OK"

def pid_check(pid,time_out):
	global g_pids
	#check for PID watchdog timeout (seconds)
	if pid in g_pids.keys():
		dt = time.time() - g_pids[pid]['watchdog_reset']
		if dt > time_out:
			return "NOK"
		else:
			return "OK"
	else:
		return "NOK"

def pid_remove(pid):
	global g_pids
	try:
		g_pids.pop(pid)
	except:
		pass
	return "OK"


def pid_msg(pid,msg):
	global g_pids
	#append a message to the PID buffer
	if pid in g_pids.keys(): #existing pid
		g_pids[pid]['msg_buffer'] += msg + '\n'
		#limit the message buffer size
		if len(g_pids[pid]['msg_buffer']) > MAX_PID_MESSAGE_BUFFER_SIZE:
			g_pids[pid]['msg_buffer'] = g_pids[pid]['msg_buffer'][-1 * MAX_PID_MESSAGE_BUFFER_SIZE:]
		return "OK"
	else:
		return "NOK"

def pid_list(ping_seconds=9999999):
	global g_pids
	pids = []
	for pid in g_pids.keys():
		if pid_check(pid,ping_seconds) == "OK":
			pids.append(pid)
	return json.dumps(pids)

def get_pids():
	global g_pids
	js_pids = json.dumps(g_pids)
	#clear the message buffers
	#for pid in g_pids.keys():
	#	g_pids[pid]['msg_buffer'] = ''
	return js_pids
		
def shutdown():
	global quit
	quit = 1
	save_db()
	return 1

def save_db():
	global AUTO_BACKUP_AFTER_N_SAVES
	global g_save_counter
	g_save_counter += 1
	if g_save_counter == AUTO_BACKUP_AFTER_N_SAVES:
		g_save_counter = 0
		backup = True
	else:
		backup = False

	for quartile in [1,2,3,4]:
		gd = {'bobs':[],'high_scores':[]}
		gd['high_scores'] = json.loads(get_all_genes(quartile))
		gd['bobs'] = json.loads(get_bobs(quartile))
		if backup:
			f = open('./config/gene_server_db_backup_quartile' + str(quartile) + '.json.bak','w')
			f.write(json.dumps(gd))
			f.close()

		f = open('./config/gene_server_db_backup_quartile' + str(quartile) + '.json','w')
		f.write(json.dumps(gd))
		f.close()
	return 'OK'

def reload_db():
	reload_error = False
	#save the gene db before shut down
	print "reloading stored gene data into server..."
	for quartile in [1,2,3,4]:
		try:
			f = open('./config/gene_server_db_backup_quartile' + str(quartile) + '.json','r')
			d = json.loads(f.read())
			f.close()

			for g in d['bobs']:
				put_bob(json.dumps(g),quartile)
			for g in d['high_scores']:
				put_gene(json.dumps(g),quartile)
		except:
			reload_error = True
			pass

	#try to restore from backup on error
	if reload_error == True:
		reload_error = False
		for quartile in [1,2,3,4]:
			try:
				f = open('./config/gene_server_db_backup_quartile' + str(quartile) + '.json.bak','r')
				d = json.loads(f.read())
				f.close()

				for g in d['bobs']:
					put_bob(json.dumps(g),quartile)
				for g in d['high_scores']:
					put_gene(json.dumps(g),quartile)
			except:
				reload_error = True
				pass

	if reload_error == True:
		return "NOK"
	return "OK"



#set the service url
class RequestHandler(SimpleXMLRPCRequestHandler):
	rpc_paths = ('/gene','/RPC2')

#create the server
server = SimpleXMLRPCServer((__server__, __port__),requestHandler = RequestHandler,logRequests = True, allow_none = True)

#register the functions
#client services
server.register_function(get_target,'get_target')
server.register_function(put_target,'put_target')
server.register_function(get_gene,'get')
server.register_function(get_all_genes,'get_all')
server.register_function(put_gene,'put')
server.register_function(put_bob,'put_bob')
server.register_function(get_bobs,'get_bobs')
#process monitoring services
server.register_function(pid_alive,'pid_alive')
server.register_function(pid_check,'pid_check')
server.register_function(pid_remove,'pid_remove')
server.register_function(pid_remove,'pid_exit')
server.register_function(pid_msg,'pid_msg')
server.register_function(get_pids,'get_pids')
server.register_function(pid_list,'pid_list')
#debug services
server.register_function(echo,'echo')
#system services
server.register_function(shutdown,'shutdown')
server.register_function(reload_db,'reload')
server.register_function(save_db,'save')
server.register_introspection_functions()

if __name__ == "__main__":
	print "gene_server: running on port %s"%__port__
	while not quit:
		server.handle_request()

