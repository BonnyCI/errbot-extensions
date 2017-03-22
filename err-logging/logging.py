from datetime import datetime
import os
from errbot import BotPlugin
from types import MethodType

log_root = "./logs"


class Logging(BotPlugin):

    def activate(self):
        super().activate()
        self.log.info(self._bot.conn.__class__.__name__)
        
        def patched_pubnotice(self, connection, event):
            message = "*** NOTICE({}) {}".format(event.source.nick, " ".join(event.arguments))
            Logging.log_to_file(datetime.utcnow(), event.target, message)
        self._bot.conn.on_pubnotice = MethodType(patched_pubnotice, self._bot.conn)

        def patched_action(self, connection, event):
            message = "* {} {}".format(event.source.nick, " ".join(event.arguments))
            Logging.log_to_file(datetime.utcnow(), event.target, message)
        self._bot.conn.on_action = MethodType(patched_action, self._bot.conn)

        original_join = self._bot.conn.on_join
        def patched_join(self, connection, event):
            message = "*** {} has joined {}".format(event.source.nick, event.target)
            Logging.log_to_file(datetime.utcnow(), event.target, message)
            original_join(connection, event)
        self._bot.conn.on_join = MethodType(patched_join, self._bot.conn)

        original_part = self._bot.conn.on_part
        def patched_part(self, connection, event):
            message = "*** {} has quit IRC".format(event.source.nick)
            Logging.log_to_file(datetime.utcnow(), event.target, message)
            original_part(connection, event)
        self._bot.conn.on_part = MethodType(patched_part, self._bot.conn)

        original_topic = self._bot.conn.on_topic
        def patched_topic(self, connection, event):
            message = "*** {} changes topic to \"{}\"".format(event.source.nick, "".join(event.arguments))
            Logging.log_to_file(datetime.utcnow(), event.target, message)
            original_topic(connection, event)
        self._bot.conn.on_topic = MethodType(patched_topic, self._bot.conn)

    @staticmethod
    def assert_directory(path):
        path = path.replace("#", "")  # remove the # in the channel name
        directory = os.path.dirname(path)
        if not os.path.exists(directory):
            os.makedirs(directory)
        return directory

    @staticmethod
    def log_to_file(timestamp, channel, message):
        channel_log_path = Logging.assert_directory("{}/{}/".format(log_root, channel))
        filename = "{}/{}.txt".format(channel_log_path, timestamp.date())
        with open(filename, "a") as f:
            f.write("{}  {}\n".format(timestamp.strftime("%Y-%m-%dT%H:%M:%S"), message))

    def callback_message(self, mess):
        if mess.is_group or mess.to.nick.startswith('#'):
            message = "<{}> {}".format(mess.frm.nick, mess.body)
            self.log_to_file(datetime.utcnow(), mess.to, message)
