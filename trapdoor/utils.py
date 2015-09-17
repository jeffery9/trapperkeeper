import urllib

import tornado.web

from trapdoor.settings import settings


# Redis modules.
import brukva

# General modules.
import os, os.path
import logging
import sys
from threading import Timer
import string
import random

# Tornado modules.
import tornado.ioloop
import tornado.web
import tornado.websocket
import tornado.auth
import tornado.options
import tornado.escape
from tornado import gen

# Redis modules.
import brukva


class TrapdoorHandler(tornado.web.RequestHandler):

    def initialize(self):
        self.db = self.application.my_settings.get("db_session")()
        self.debug = self.application.my_settings.get("debug", False)
        self.debug_user = self.application.my_settings.get("debug_user")

    def on_finish(self):
        self.db.close()

    def render_template(self, template_name, **kwargs):
        template = self.application.my_settings["template_env"].get_template(template_name)
        content = template.render(kwargs)
        return content

    def render(self, template_name, **kwargs):
        kwargs.update(self.get_template_namespace())
        self.write(self.render_template(template_name, **kwargs))

    def notfound(self):
        self.set_status(404)
        self.render("errors/notfound.html")


class ChatSocketHandler(tornado.websocket.WebSocketHandler):
    """
    Handler for dealing with websockets. It receives, stores and distributes new messages.

    TODO: Not proper authentication handling!
    """

    @gen.engine
    def open(self, room='root'):
        """
        Called when socket is opened. It will subscribe for the given chat room based on Redis Pub/Sub.
        """
        # Check if room is set.
        if not room:
            self.write_message({'error': 1, 'textStatus': 'Error: No room specified'})
            self.close()
            return
        self.room = str(room)
        self.new_message_send = False
        # Create a Redis connection.
        self.client = redis_connect()
        # Subscribe to the given chat room.
        self.client.subscribe(self.room)
        self.subscribed = True
        self.client.listen(self.on_messages_published)
        logging.info('New user connected to chat room ' + room)


    def on_messages_published(self, message):
        """
        Callback for listening to subscribed chat room based on Redis Pub/Sub. When a new message is stored
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
            self.application.client.rpush(self.room, message_encoded)
            # Publish message in Redis channel.
            self.application.client.publish(self.room, message_encoded)
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
                self.client.unsubscribe(self.room)
                self.subscribed = False
            # Disconnect connection after delay due to this issue:
            # https://github.com/evilkost/brukva/issues/25
            t = Timer(0.1, self.client.disconnect)
            t.start()




def print_date(date_obj):
    if date_obj is None:
        return ""

    date_obj = date_obj.astimezone(settings["timezone"])
    return date_obj.strftime(settings["date_format"])


jinja2_filters = {
    "print_date": print_date,
}


def update_qs(qs, **kwargs):
    qs = qs.copy()
    qs.update(kwargs)
    return "?" + urllib.urlencode(qs, True)

jinja2_globals = {
    "update_qs": update_qs,
}

def redis_connect():
    """
    Established an asynchronous resi connection.
    """
    # Get Redis connection settings for Heroku with fallback to defaults.
    redistogo_url = os.getenv('REDISTOGO_URL', None)
    if redistogo_url == None:
        REDIS_HOST = 'localhost'
        REDIS_PORT = 6379
        REDIS_PWD = None
        REDIS_USER = None
    else:
        redis_url = redistogo_url
        redis_url = redis_url.split('redis://')[1]
        redis_url = redis_url.split('/')[0]
        REDIS_USER, redis_url = redis_url.split(':', 1)
        REDIS_PWD, redis_url = redis_url.split('@', 1)
        REDIS_HOST, REDIS_PORT = redis_url.split(':', 1)
    client = brukva.Client(host=REDIS_HOST, port=int(REDIS_PORT), password=REDIS_PWD)
    client.connect()
    return client
