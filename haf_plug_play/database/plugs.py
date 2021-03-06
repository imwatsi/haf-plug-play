import json
from threading import Thread
import time
from typing import Dict

from haf_plug_play.database.core import DbSession


class Plug:

    def __init__(self, name, defs) -> None:
        self.name = name
        self.defs = defs
        self.db_conn = DbSession()
        self.error = False
    
    def create_new_connection(self):
        if self.error == False:
            del self.db_conn
            self.db_conn = DbSession()

    def get_defs(self):
        return self.defs
    
    def disable(self):
        self.defs['props']['enabled'] = False
        _defs = json.dumps(self.defs)
        self.db_conn.execute(
            f"UPDATE hpp.plug_state SET defs = '{_defs}' WHERE plug = '{self.name}';"
        )
        self.db_conn.commit()
    
    def enable(self):
        self.defs['props']['enabled'] = True
        _defs = json.dumps(self.defs)
        self.db_conn.execute(
            f"UPDATE hpp.plug_state SET defs = '{_defs}' WHERE plug = '{self.name}';"
        )
        self.db_conn.commit()
    
    def terminate_sync(self):
        self.db_conn.execute(
            f"SELECT hpp.terminate_sync({self.name});"
        )
    
    def is_enabled(self):
        enabled = bool(
            self.db_conn.select_one(
                f"SELECT defs->'props'->'enabled' FROM hpp.plug_state WHERE plug ='{self.name}';"
            )
        )
        return enabled

    def is_connection_open(self):
        return self.db_conn.is_open()
    
    def running(self):
        running = self.db_conn.select_one(
            f"SELECT hpp.plug_running('{self.name}');")
        return running
    
    def is_long_running(self):
        long_running = self.db_conn.select_one(
            f"SELECT hpp.plug_long_running('{self.name}');")
        return long_running
    
    def start(self):
        try:
            if self.is_enabled():
                print(f"{self.name}:: starting")
                self.db_conn.execute(f"CALL hpp.sync_plug( '{self.name}' );")
        except Exception as err:
            print(f"Plug error: '{self.name}'")
            print(err)
            self.error = True
            self.disable()
            self.db_conn.conn.close()
            self.db_conn.conn.close()

class AvailablePlugs:

    plugs = dict[str, Plug]()

    @classmethod
    def add_plug(cls, plug_name, plug:Plug):
        cls.plugs[plug_name] = plug

    @classmethod
    def plug_watch(cls):
        while True:
            for _plug in cls.plugs.items():
                plug = cls.plugs[_plug[0]]
                if not plug.error:
                    good = plug.is_connection_open()
                    if good is False:
                        print(f"{_plug[0]}:: creating new DB connection.")
                        plug.create_new_connection()
                    if plug.running() is False:
                        Thread(target=plug.start).start()
                    elif plug.is_long_running():
                        plug.terminate_sync()
            time.sleep(60)
