""" Standup plugin for errbot """
from datetime import datetime
import os
import sqlite3
import pytz

from errbot import BotPlugin, botcmd

STANDUP_HOUR = 10

class Standup(BotPlugin):
    """ Standup class for errbot """

    # Initialization

    def activate(self):
        """ Initial entrypoint to plugin """
        self.userdata = {
            'timezones': [
                {'timezone': 'Australia/Sydney',
                 'users': ['jamielennox'], },
                {'timezone': 'America/New_York',
                 'users': ['olaph'], },
                {'timezone': 'America/Chicago',
                 'users': ['eventingmonkey',
                           'eggshell'], },
                {'timezone': 'America/Los_Angeles',
                 'users': ['adam_g',
                           'auggy',
                           'jlk',
                           'rattboi',
                           'SpamapS',
                           'jesusaur'], }]}

        self.initialize_scheduler()
        db_ok = self.initialize_database()
        if db_ok:
            super(Standup, self).activate()

    def initialize_database(self):
        """Creates standup database if it doesn't exist"""
        standup_db = os.path.join(self.plugin_dir, 'standup.sqlite')
        self.con = None
        try:
            self.con = sqlite3.connect(standup_db, check_same_thread=False)
            with self.con as con:
                con.execute("""create table if not exists statuses
                                (id integer primary key,
                                 date text default CURRENT_DATE,
                                 status text not null,
                                 author text default 'unknown');""")
        except sqlite3.Error as e:
            self.log.error(e)
        return self.con is not None

    def initialize_scheduler(self):
        self.start_poller(60, self.check_for_scheduled_standups)

    # Scheduler tasks

    def check_for_scheduled_standups(self):
        timezones = [group['timezone'] for group in self.userdata['timezones']]
        now = datetime.utcnow()
        for timezone in timezones:
            local_now = self.utc_to_timezone(now, timezone)
            if local_now.hour == STANDUP_HOUR and local_now.weekday() < 6:  # M-F
                users = self.get_local_users(timezone, timezones)
                self.notify_users(users)

    @staticmethod
    def get_local_users(timezone, timezones):
        results = [group['users'] for group in timezones if group['timezone'] == timezone]
        if len(results) == 1:
            return results[0]
        else:
            return []

    def notify_users(self, users):
        for user in users:
            self.send(self.build_identifier(user),
                      "Hey {}, it's time for your standup!".format(user))

    @staticmethod
    def utc_to_timezone(some_date, tz):
        return some_date.replace(tzinfo=pytz.timezone('UTC')).astimezone(pytz.timezone(tz))

    # Bot commands section

    @botcmd
    def standup(self, msg, args):
        return self.standup_help(msg, args)

    @botcmd
    def standup_help(self, msg, args):
        """Gives the user info on how to use the standup plugin
           usage: !standup help"""
        lines = ["!standup add <status> -- Add a status to today's standup (can be done multiple times)",
                 "!standup get          -- Get all of today's statuses for your user (to review or delete)",
                 "!standup delete <id>  -- Delete a status from today's standup"]
        return '\n'.join(lines)

    @botcmd
    def standup_add(self, msg, args):
        """Adds a new status
           usage: !standup add <status>"""
        if args == '':
            return "Usage: !standup add <status>"
        user = msg.frm.nick
        timezone = self.lookup_timezone_from_user(user, self.userdata['timezones'])
        if timezone is None:
            self.log.debug("Couldn't find timezone for user: {}".format(user))
        else:
            local_now = self.utc_to_timezone(datetime.utcnow(), timezone)
            local_date = local_now.date()
            self.db_insert_status(self.con, user, args, local_date)
            return "added: {}".format(args)

    @staticmethod
    def lookup_timezone_from_user(user, timezones):
        results = [group['timezone'] for group in timezones if user in group['users']]
        if len(results) == 1:
            return results[0]
        else:
            return None

    @staticmethod
    def db_insert_status(db_conn, author, status, date):
        with db_conn as c:
            c.execute("""INSERT INTO statuses (status, author, date) VALUES (?,?,?)""", (status, author, date))

    @botcmd
    def standup_get(self, msg, args):
        """Gets all statuses for a specific user for today
           usage: !standup get"""
        author = msg.frm.nick
        date = datetime.utcnow().date() if args == '' else args
        yield "Statuses for {} on {}".format(author, date)
        statuses = self.db_get_status_from_author_and_date(self.con, author, date)
        for status in statuses:
            yield "{}: {}".format(status['id'], status['status'])

    @staticmethod
    def db_get_status_from_author_and_date(db_conn, author, date):
        cur = db_conn.cursor()
        cur.execute("""SELECT id, status FROM statuses WHERE author=? AND date=?""", (author, date))
        results = [{'id': row[0], 'status': row[1]} for row in cur]
        return results

    @botcmd
    def standup_delete(self, msg, args):
        """Delete statuses for a specific user by id
           usage: !standup delete <id>"""
        if args == '':
            return "Usage: !standup delete <id>"
        status_id = None
        try:
            status_id = int(args)
        except:
            return "Invalid id: {}".format(args)
        author = msg.frm.nick
        today = datetime.utcnow().date()
        count = self.db_delete_status_by_id(self.con, status_id, author, today)
        if count > 0:
            return "deleted: id {}".format(status_id)
        else:
            return "couldn't delete id {}".format(status_id)

    @staticmethod
    def db_delete_status_by_id(db_conn, status_id, author, date):
        cur = db_conn.cursor()
        cur.execute("""DELETE FROM statuses WHERE id=? AND author=? AND date=?""", (status_id, author, date))
        db_conn.commit()
        return cur.rowcount
