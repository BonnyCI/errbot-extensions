""" Standup plugin for errbot """
from datetime import datetime
import os
import sqlite3

from errbot import BotPlugin, botcmd


class Standup(BotPlugin):
    """ Standup class for errbot """

    def activate(self):
        """ Initial entrypoint to plugin """
        self.initialize_scheduler()
        db_ok = self.initialize_database()
        if db_ok:
            super().activate()

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
        return (self.con != None)

    def initialize_scheduler(self):
        self.start_poller(60, self.check_for_scheduled_standups)

    def check_for_scheduled_standups(self):
        self.log.debug('I am called every minute')

    @botcmd(admin_only=True)
    def standup_add(self, msg, args):
        """Adds a new status, usage: !standup add <status>"""
        if args == '':
            return "Usage: !standup add <status>"
        author = msg.frm.nick
        with self.con as c:
            c.execute("""INSERT INTO statuses (status, author) VALUES (?,?)""", (args, author))

        return "added: {}".format(args)

    @botcmd(admin_only=True)
    def standup_get(self, msg, args):
        """Gets all statuses for a specific user for today, usage: !standup get"""
        date = None
        if args == '':
            date = datetime.utcnow().date() 
        else:
            date = args
        author = msg.frm.nick
        cur = self.con.cursor()
        cur.execute("""SELECT id, status, author FROM statuses WHERE author=? AND date=?""", (author, date))
        yield "Statuses for {} on {}".format(author, date)
        for row in cur:
            yield "{}: {}".format(row[0], row[1])

    @botcmd(admin_only=True)
    def standup_delete(self, msg, args):
        """Delete statuses for a specific user by id, usage: !standup delete <id>"""
        if args == '':
            return "Usage: !standup delete <id>"
        status_id = None
        try:
            status_id = int(args)
        except:
            return "Invalid id: {}".format(args)
        author = msg.frm.nick
        today = datetime.utcnow().date()
        cur = self.con.cursor()
        cur.execute("""DELETE FROM statuses WHERE id=? AND author=? AND date=?""", (status_id, author, today))
        self.con.commit()
        if cur.rowcount > 0:
            return "deleted: id {}".format(args)
        else:
            return "couldn't delete id {}".format(args)
