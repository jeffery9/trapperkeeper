from datetime import datetime
import json
import logging
import string
import random
import sys
from threading import Timer

import tornadoredis
import tornado
from sqlalchemy import desc, or_

from tornado import gen

from trapdoor.utils import TrapdoorHandler
from trapperkeeper.models import Notification, VarBind


def filter_query(query, host, oid, severity):
    if host is not None:
        query = query.filter(Notification.host == host)

    if oid is not None:
        query = query.filter(Notification.oid == oid)

    if severity is not None:
        query = query.filter(Notification.severity == severity)

    return query


def _get_traps(db, offset=0, limit=50, host=None, oid=None, severity=None):
    now = datetime.utcnow()

    active_query = (db
        .query(Notification)
        .filter(or_(
            Notification.expires >= now,
            Notification.expires == None
         ))
        .order_by(desc(Notification.sent))
    )
    active_query = filter_query(active_query, host, oid, severity)

    total_active = active_query.count()
    traps = active_query.offset(offset).limit(limit).all()
    num_active = len(traps)

    if num_active:
        remaining_offset = 0
    else:
        remaining_offset = offset - total_active
        if remaining_offset < 0:
            remaining_offset = 0

    if num_active < limit:
        expired_query = (db
            .query(Notification)
            .filter(Notification.expires < now)
            .order_by(desc(Notification.sent))
        )
        expired_query = filter_query(expired_query, host, oid, severity)
        traps += expired_query.offset(remaining_offset).limit(limit - num_active).all()

    return traps, num_active


class Index(TrapdoorHandler):
    def get(self):
        offset = int(self.get_argument("offset", 0))
        limit = int(self.get_argument("limit", 50))
        if limit > 100:
            limit = 100

        host = self.get_argument("host", None)
        if host is None:
            host = self.get_argument("hostname", None)
        oid = self.get_argument("oid", None)
        severity = self.get_argument("severity", None)

        now = datetime.utcnow()
        traps, num_active = _get_traps(self.db, offset, limit, host, oid, severity)

        return self.render(
            "index.html", traps=traps, now=now, num_active=num_active,
            host=host, oid=oid, severity=severity, offset=offset, limit=limit)


class Resolve(TrapdoorHandler):
    def post(self):
        host = self.get_argument("host")
        oid = self.get_argument("oid")

        now = datetime.utcnow()

        traps = (self.db.query(Notification)
            .filter(
                Notification.host == host,
                Notification.oid == oid,
                or_(
                    Notification.expires >= now,
                    Notification.expires == None
                )
            )
            .all()
        )

        for trap in traps:
            trap.expires = now
        self.db.commit()

        return self.redirect("/")

class ResolveAll(TrapdoorHandler):
    def post(self):

        now = datetime.utcnow()
        traps = (self.db.query(Notification)
            .filter(
                or_(
                    Notification.expires >= now,
                    Notification.expires == None
                )
            )
            .all()
        )

        for trap in traps:
            trap.expires = now
        self.db.commit()

        return self.redirect("/")

class NotFound(TrapdoorHandler):
    def get(self):
        return self.notfound()


class ApiVarBinds(TrapdoorHandler):
    def get(self, notification_id):
        varbinds = self.db.query(VarBind).filter(VarBind.notification_id == notification_id).all()
        varbinds = [varbind.to_dict(True) for varbind in varbinds]
        self.write(json.dumps(varbinds))


class ApiActiveTraps(TrapdoorHandler):
    def get(self):

        now = datetime.utcnow()
        host = self.get_argument("host", None)
        if host is None:
            host = self.get_argument("hostname", None)
        oid = self.get_argument("oid", None)
        severity = self.get_argument("severity", None)

        active_query = (self.db
            .query(
                Notification.host,
                Notification.oid,
                Notification.severity)
            .filter(or_(
                Notification.expires >= now,
                Notification.expires == None
             ))
            .group_by(Notification.host, Notification.oid)
            .order_by(desc(Notification.sent))
        )
        active_query = filter_query(active_query, host, oid, severity)

        traps = active_query.all()
        self.write(json.dumps(traps))


class ApiTraps(TrapdoorHandler):
    def get(self):
        offset = int(self.get_argument("offset", 0))
        limit = int(self.get_argument("limit", 10))
        if limit > 100:
            limit = 100

        host = self.get_argument("host", None)
        if host is None:
            host = self.get_argument("hostname", None)
        oid = self.get_argument("oid", None)
        severity = self.get_argument("severity", None)

        now = datetime.utcnow()
        traps, num_active = _get_traps(self.db, offset, limit, host, oid, severity)

        self.write(json.dumps([trap.to_dict() for trap in traps]))

class ChatSocketHandler(tornado.websocket.WebSocketHandler):
    """
    Handler for dealing with websockets. It receives, stores and distributes new messages.

    TODO: Not proper authentication handling!
    """

    @gen.engine
    def open(self, channel='root'):
        """
        Called when socket is opened. It will subscribe for the given chat channel based on Redis Pub/Sub.
        """
        # Check if channel is set.
        if not channel:
            self.write_message({'error': 1, 'textStatus': 'Error: No channel specified'})
            self.close()
            return
        self.channel = str(channel)
        self.new_message_send = False
        # Create a Redis connection.
        self.client = tornadoredis.Client()
        self.client.connect()
        # Subscribe to the given chat channel.
        self.client.subscribe(self.channel)
        self.subscribed = True
        self.client.listen(self.on_messages_published)
        logging.info('New user connected to chat channel ' + channel)


    def on_messages_published(self, message):
        """
        Callback for listening to subscribed chat channel based on Redis Pub/Sub. When a new message is stored
        in the given Redis chanel this method will be called.
        """
        # Decode message
        m = tornado.escape.json_decode(message.body)
        # Send messages to other clients and finish connection.
        self.write_message(dict(messages=[m]))


    def on_message(self, data):
        """
        Callback when new message received vie the socket.
        """
        logging.info('Received new message %r', data)
        try:
            # Parse input to message dict.
            datadecoded = tornado.escape.json_decode(data)
            message = {
                '_id': ''.join(random.choice(string.ascii_uppercase) for i in range(12)),
                'from': self.get_secure_cookie('user', str(datadecoded['user'])),
                'body': tornado.escape.linkify(datadecoded["body"]),
            }
            if not message['from']:
                logging.warning("Error: Authentication missing")
                message['from'] = 'Guest'
        except Exception, err:
            # Send an error back to client.
            self.write_message({'error': 1, 'textStatus': 'Bad input data ... ' + str(err) + data})
            return

        # Save message and publish in Redis.
        try:
            # Convert to JSON-literal.
            message_encoded = tornado.escape.json_encode(message)
            # Persistently store message in Redis.
            self.application.client.rpush(self.channel, message_encoded)
            # Publish message in Redis channel.
            self.application.client.publish(self.channel, message_encoded)
        except Exception, err:
            e = str(sys.exc_info()[0])
            # Send an error back to client.
            self.write_message({'error': 1, 'textStatus': 'Error writing to database: ' + str(err)})
            return

        # Send message through the socket to indicate a successful operation.
        self.write_message(message)
        return


    def on_close(self):
        """
        Callback when the socket is closed. Frees up resource related to this socket.
        """
        logging.info("socket closed, cleaning up resources now")
        if hasattr(self, 'client'):
            # Unsubscribe if not done yet.
            if self.subscribed:
                self.client.unsubscribe(self.channel)
                self.subscribed = False
            # Disconnect connection after delay due to this issue:
            # https://github.com/evilkost/brukva/issues/25
            t = Timer(0.1, self.client.disconnect)
            t.start()
