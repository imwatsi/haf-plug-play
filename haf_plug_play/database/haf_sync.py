import os
import psycopg2

APPLICATION_CONTEXT = "plug_play"

config = {
    'db_username': 'postgres',
    'db_password': 'pass.word',
    'server_host': '0.0.0.0',
    'server_port': '8080',
    'ssl_cert': '',
    'ssl_key': ''
}

class DbSession:
    def __init__(self):
        # TODO: retrieve from env_variables
        self.conn = psycopg2.connect(f"dbname=haf user={config['db_username']} password={config['db_password']}")
        self.conn.autocommit = False
        self.cur = self.conn.cursor()
    
    def select(self, sql):
        self.cur.execute(sql)
        res = self.cur.fetchall()
        if len(res) == 0:
            return None
        else:
            return res
    
    def execute_immediate(self, sql,  data):
        self.cur.execute(sql, data)
        self.conn.commit()
    
    def get_query(self,sql, data):
        return self.cur.mogrify(sql,data)
    
    def execute(self, sql, data):
        try:
            if data:
                self.cur.execute(sql, data)
            else:
                self.cur.execute(sql)

        except Exception as e:
            print(e)
            print(f"SQL:  {sql}")
            print(f"DATA:   {data}")
            self.conn.rollback()
            raise Exception ('DB error occurred')
    
    def commit(self):
        self.conn.commit()


class DbSetup:

    @classmethod
    def check_db(cls):
        # check if it exists
        try:
            # TODO: retrieve authentication from config 
            cls.conn = psycopg2.connect(f"dbname=haf user={config['db_username']} password={config['db_password']}")
        except psycopg2.OperationalError as e:
            if "haf" in e.args[0] and "does not exist" in e.args[0]:
                print("No database found. Please create a 'haf' database in PostgreSQL.")
                os._exit(1)
            else:
                print(e)
                os._exit(1)
    
    @classmethod
    def prepare_app_data(cls):
        # prepare app data
        db = DbSession()
        exists = db.select(
            f"SELECT hive.app_context_exists( '{APPLICATION_CONTEXT}' );"
        )[0]
        print(exists)
        if exists == False:
            db.select(f"SELECT hive.app_create_context( '{APPLICATION_CONTEXT}' );")
            db.commit()
        # create table
        db.execute(
            f"""
                CREATE TABLE IF NOT EXISTS public.plug_play_ops(
                    id integer PRIMARY KEY,
                    block_num integer NOT NULL,
                    req_auths varchar(256),
                    req_posting_auths varchar(256),
                    op_id varchar(128) NOT NULL,
                    op_json varchar(5096) NOT NULL
                )
                INHERITS( hive.{APPLICATION_CONTEXT} );
            """, None
        )
        db.execute(
            f"""
                CREATE TABLE IF NOT EXISTS public.app_sync(
                    app_name varchar(32),
                    reversible_block integer DEFAULT 0,
                    irreversible_block integer DEFAULT 0
                );
            """, None
        )
        db.execute(
            f"""
                CREATE TABLE IF NOT EXISTS public.apps(
                    app_name varchar(32),
                    op_ids varchar(16)[],
                    last_updated timestamp
                );
            """, None
        )
        db.commit()
        # create update ops functions
        db.execute(
            f"""
                CREATE OR REPLACE FUNCTION public.update_plug_play_ops( _first_block INT, _last_block INT )
                RETURNS void
                LANGUAGE plpgsql
                VOLATILE AS $function$
                    BEGIN
                        INSERT INTO public.plug_play_ops as ppops(
                            id, block_num, req_auths, req_posting_auths, op_id, op_json)
                        SELECT 
                            id,
                            block_num,
                            body::json -> 'value' -> 'required_auths',
                            body::json -> 'value' -> 'required_posting_auths',
                            body::json->'value'->'id',
                            body::json->'value'->'json'
                        FROM hive.{APPLICATION_CONTEXT}_operations_view ppov
                        WHERE ppov.block_num >= _first_block AND ppov.block_num <= _last_block
                        AND ppov.op_type_id = 18;
                    END;
                    $function$
            """, None
        )
        db.commit()
        cls.conn.close()
    

def main_loop():
    while True:
        db = DbSession()
        # get blocks range
        blocks_range = db.select(f"SELECT * FROM hive.app_next_block('{APPLICATION_CONTEXT}');")[0]
        print(f"Blocks range: {blocks_range}")
        if not blocks_range:
            continue
        (first_block, last_block) = blocks_range
        if not first_block:
            continue

        if (last_block - first_block) > 100:
            db.select(f"SELECT hive.app_context_detach( '{APPLICATION_CONTEXT}' );")
            print("context detached")
            db.select(f"SELECT public.update_plug_play_ops( {first_block}, {last_block} );")
            print("massive sync done")
            db.select(f"SELECT hive.app_context_attach( '{APPLICATION_CONTEXT}', {last_block} );")
            print("context attached again")
            db.commit()
            continue

        print(db.select(f"SELECT public.update_plug_play_ops( {first_block}, {last_block} );"))
        db.commit()
        

DbSetup.check_db()
DbSetup.prepare_app_data()
#main_loop()