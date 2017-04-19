""" Standup plugin for errbot """
from datetime import datetime
import sqlite3
import pytz
import yaml

from errbot import BotPlugin, botcmd


class Standup(BotPlugin):
    """ Standup class for errbot """

    # Initialization

    def activate(self):
        """ Initial entrypoint to plugin """
        if hasattr(self.bot_config, 'STANDUP_CONFIG_PATH'):
            standup_config_file = self.bot_config.STANDUP_CONFIG_PATH
        else:
            standup_config_file = '/etc/standup/config.yaml'
        config_file = open(standup_config_file, 'r')
        self.config = yaml.safe_load(config_file)

        self.staged = {}
        self.notified = {}
        self.initialize_scheduler()
        db_ok = self.initialize_database(self.config.get('database_path'))
        if db_ok:
            super(Standup, self).activate()

    def initialize_database(self, path_to_db_file):
        """Creates standup database if it doesn't exist"""
        self.con = None
        try:
            self.con = sqlite3.connect(path_to_db_file, check_same_thread=False)
            with self.con as con:
                con.execute("""create table if not exists statuses
                                (id integer primary key,
                                 date text default CURRENT_DATE,
                                 yesterday text not null,
                                 today text not null,
                                 blockers text not null,
                                 author text default 'unknown');""")
        except sqlite3.Error as e:
            self.log.error(e)
        return self.con is not None

    def initialize_scheduler(self):
        self.start_poller(60, self.check_for_scheduled_standups)

    # Scheduler tasks

    def check_for_scheduled_standups(self):
        tz_config = self.config.get('timezones', [])
        timezones = [group['timezone'] for group in tz_config]
        local_notification_hour = self.config.get('local_notification_hour', 10)

        now = datetime.utcnow()
        for timezone in timezones:
            local_now = self.utc_to_timezone(now, timezone)
            users = self.get_local_users(timezone, tz_config)
            if local_now.hour == local_notification_hour and local_now.weekday() < 5:  # M-F
                self.notify_users(users)
            else:
                self.clear_notified(users)

    @staticmethod
    def get_local_users(timezone, timezones):
        results = [group['users'] for group in timezones if group['timezone'] == timezone]
        if len(results) == 1:
            return results[0]
        else:
            return []

    def notify_users(self, users):
        for user in users:
            if self.notified.get(user, False) == False:
                try:
                    self.send(self.build_identifier(user),
                              "Hey {}, it's time for your standup! Use '!standup start' to begin".format(user))
                    self.notified[user] = True
                except:
                    self.notified[user] = False

    def clear_notified(self, users):
        for user in users:
            self.notified[user] = False

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
        lines = ["!standup start                             -- Start today's standup",
                 "!standup yesterday/today/blockers <status> -- Add to today's standup",
                 "!standup review                            -- Review today's uncommitted standup",
                 "!standup commit                            -- Commit today's standup",
                 "!standup log                               -- Show today's committed standup for your user (to review or delete)",
                 "!standup delete <id>                       -- Delete today's standup",
                 "!standup team <date>                       -- Show team's standup for date (default = today)"]
        return '\n'.join(lines)

    @botcmd
    def standup_start(self, msg, args):
        user = msg.frm.nick
        self.clear_stage(user)
        return "Please use '!standup yesterday/today/blockers' to stage your standup, and '!standup commit' when you're done"

    def clear_stage(self, user):
        self.staged[user] = {}

    @botcmd
    def standup_yesterday(self, msg, args):
        return self.standup_set_part(msg.frm.nick, 'yesterday', args)

    @botcmd
    def standup_today(self, msg, args):
        return self.standup_set_part(msg.frm.nick, 'today', args)

    @botcmd
    def standup_blockers(self, msg, args):
        return self.standup_set_part(msg.frm.nick, 'blockers', args)

    def standup_set_part(self, user, part, status):
        staged = self.get_staging(user)
        self.log.debug(staged)
        if staged is not None:
            staged[part] = status
            self.log.debug("was staged")
            return
        else:
            self.log.debug("not staged")
            return "you need to '!standup start' first"

    def get_staging(self, user):
        return self.staged.get(user, None)

    @botcmd
    def standup_review(self, msg, args):
        user = msg.frm.nick
        staged = self.staged.get(user, {})
        for part in ['yesterday', 'today', 'blockers']:
            yield "{}: {}".format(part, staged.get(part, '<unset>'))

    def get_local_date_for_user(self, user, timezones):
        timezone = self.lookup_timezone_from_user(user, timezones)
        if timezone is None:
            self.log.debug("Couldn't find timezone for user: {}".format(user))
            return None
        else:
            local_now = self.utc_to_timezone(datetime.utcnow(), timezone)
            return local_now.date()

    @botcmd
    def standup_commit(self, msg, args):
        """Adds a new status
           usage: !standup commit"""
        user = msg.frm.nick
        staged = self.staged.get(user, None)
        if staged == None:
            return "you need to '!standup start' first"
        for part in ['yesterday', 'today', 'blockers']:
            if part not in staged:
                return "{}: not all field filled. Use '!standup review' to determine which fields are missing".format(part)
        local_date = self.get_local_date_for_user(user, self.config["timezones"])
        existing_statuses = self.db_get_status_from_author_and_date(self.con, user, local_date)
        if len(existing_statuses) > 0:
            return "Oops, previous standup already committed for today. Please use '!standup delete' to remove prior standup"
        else:
            self.db_insert_status(self.con, user, staged, local_date)
            self.clear_stage(user)
            return "Standup committed. Use '!standup log' to see committed standup, or '!standup delete' to redo today's standup"

    @staticmethod
    def lookup_timezone_from_user(user, timezones):
        results = [group['timezone'] for group in timezones if user in group['users']]
        if len(results) == 1:
            return results[0]
        else:
            return None

    @staticmethod
    def db_insert_status(db_conn, author, status, date):
        yesterday = status['yesterday']
        today = status['today']
        blockers = status['blockers']
        with db_conn as c:
            c.execute("""INSERT INTO statuses (yesterday, today, blockers, author, date) VALUES (?,?,?,?,?)""", (yesterday, today, blockers, author, date))

    @botcmd
    def standup_log(self, msg, args):
        """Shows statuses for a specific user for today
           usage: !standup log"""
        user = msg.frm.nick
        local_date = self.get_local_date_for_user(user, self.config["timezones"])
        date = local_date if args == '' else args
        yield "Statuses for {} on {}".format(user, date)
        statuses = self.db_get_status_from_author_and_date(self.con, user, date)
        for status in statuses:
            yield "{}:".format(status['id'])
            yield "- yesterday: {}".format(status['yesterday'])
            yield "- today:     {}".format(status['today'])
            yield "- blockers:  {}".format(status['blockers'])

    @staticmethod
    def db_get_status_from_author_and_date(db_conn, author, date):
        cur = db_conn.cursor()
        cur.execute("""SELECT id, yesterday, today, blockers FROM statuses WHERE author=? AND date=?""", (author, date))
        results = [{'id': row[0],
                    'yesterday': row[1],
                    'today': row[2],
                    'blockers': row[3]} for row in cur]
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
        user = msg.frm.nick
        local_date = self.get_local_date_for_user(user, self.config["timezones"])
        count = self.db_delete_status_by_id(self.con, status_id, user, local_date)
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

    @botcmd
    def standup_team(self, msg, args):
        """Show standups for the entire team for a given day, defaults to today
           usage: !standup team <date>"""
        user = msg.frm.nick
        local_date = self.get_local_date_for_user(user, self.config["timezones"])
        date = local_date if args == '' else args
        yield "Standups for {}".format(date)
        statuses = self.db_get_statuses_from_date(self.con, date)
        for status in statuses:
            yield "{}:".format(status['author'])
            yield "- yesterday: {}".format(status['yesterday'])
            yield "- today:     {}".format(status['today'])
            yield "- blockers:  {}".format(status['blockers'])

    @staticmethod
    def db_get_statuses_from_date(db_conn, date):
        cur = db_conn.cursor()
        cur.execute("""SELECT author, yesterday, today, blockers FROM statuses WHERE date=?""", (date, ))
        results = [{'author': row[0],
                    'yesterday': row[1],
                    'today': row[2],
                    'blockers': row[3]} for row in cur]
        return results
