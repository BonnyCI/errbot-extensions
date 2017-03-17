from datetime import datetime
import os
from errbot import BotPlugin


log_root = "./logs"


class Logging(BotPlugin):

    @staticmethod
    def assert_directory(path):
        path = path.replace("#", "")  # remove the # in the channel name
        directory = os.path.dirname(path)
        if not os.path.exists(directory):
            os.makedirs(directory)
        return directory

    @staticmethod
    def format_sender(sender):    
        nick = ""
        try:
            nick = sender.nick
        except:
            nick = sender
        return nick

    @staticmethod
    def log_message_to_file(sender, receiver, timestamp, body, is_group_msg):
        if is_group_msg or receiver.nick.startswith('#'):
            channel_log_path = Logging.assert_directory("{}/{}/".format(log_root, receiver))
            filename = "{}/{}.txt".format(channel_log_path, timestamp.date())
            with open(filename, "a") as f:
                f.write("{}\t{}\t{}\n".format(timestamp.strftime("%Y-%m-%d %H:%M:%S"), Logging.format_sender(sender), body))

    def callback_message(self, mess):
        self.log_message_to_file(mess.frm,
                                 mess.to,
                                 datetime.utcnow(),
                                 mess.body,
                                 mess.is_group)
