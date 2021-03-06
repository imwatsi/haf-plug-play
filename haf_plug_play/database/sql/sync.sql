-- check context

CREATE OR REPLACE PROCEDURE hpp.sync_plug(_plug_name VARCHAR(64))
    LANGUAGE plpgsql
    AS $$
        DECLARE
            temprow RECORD;
            _app_context VARCHAR;
            _ops JSON;
            _op_ids SMALLINT[];
            _next_block_range hive.blocks_range;
            _latest_block_num INTEGER;
            _range BIGINT[];
        BEGIN
            SELECT defs->'props'->>'context' INTO _app_context FROM hpp.plug_state WHERE plug = _plug_name;
            SELECT defs->'ops' INTO _ops FROM hpp.plug_state WHERE plug = _plug_name;
            SELECT ARRAY (SELECT json_array_elements_text(defs->'op_ids')) INTO _op_ids FROM hpp.plug_state WHERE plug = _plug_name;

            IF _app_context IS NULL THEN
                RAISE NOTICE 'Could not start sync for plug: %. DB entry not found.', _plug_name;
                RETURN;
            END IF;

            SELECT latest_block_num INTO _latest_block_num FROM hpp.plug_state WHERE plug = _plug_name;
            IF NOT hive.app_context_is_attached(_app_context) THEN
                PERFORM hive.app_context_attach(_app_context, _latest_block_num);
            END IF;
            -- SELECT latest_hive_opid INTO _latest_hive_opid FROM hpp.plug_state WHERE plug = _plug_name;
            -- SELECT MAX(id) INTO _head_hive_opid FROM hive.operations; -- TODO reversible if in def
            -- start process
            WHILE hpp.plug_enabled(_plug_name) LOOP
                _next_block_range := hive.app_next_block(_app_context);
                IF _next_block_range IS NULL THEN
                    RAISE WARNING 'Waiting for next block...';
                ELSE
                    RAISE NOTICE 'Attempting to process block range: <%,%>', _next_block_range.first_block, _next_block_range.last_block;
                    CALL hpp.process_block_range(_plug_name, _app_context, _next_block_range.first_block, _next_block_range.last_block, _ops, _op_ids);
                END IF;
            END LOOP;
            COMMIT;
        END;
    $$;

CREATE OR REPLACE PROCEDURE hpp.process_block_range(_plug_name VARCHAR, _app_context VARCHAR, _start INTEGER, _end INTEGER, _ops JSON, _op_ids SMALLINT[] )
    LANGUAGE plpgsql
    AS $$

        DECLARE
            temprow RECORD;
            _plug_schema VARCHAR;
            _done BOOLEAN;
            _to_attach BOOLEAN;
            _first_block INTEGER;
            _last_block INTEGER;
            _last_block_time TIMESTAMP;
            _step INTEGER;
        BEGIN
            _to_attach := false;
            _step := 100;
            -- determine if massive sync is needed
            IF _end - _start > 0 THEN
                -- detach context
                PERFORM hive.app_context_detach(_app_context);
                RAISE NOTICE 'Context detached.';
                _to_attach := true;
            END IF;
            -- get defs
            -- _arr := ARRAY(SELECT json_array_elements_text(_ops));
            -- _op_ids := array_agg(SELECT unnest(_arr[1:999][1]));

            -- divide range
            FOR _first_block IN _start .. _end BY _step LOOP
                _last_block := _first_block + _step - 1;

                IF _last_block > _end THEN --- in case the _step is larger than range length
                    _last_block := _end;
                END IF;

                RAISE NOTICE 'Attempting to process a block range: <%, %>', _first_block, _last_block;
                -- record run start
                    -- select records and pass records to relevant functions
                FOR temprow IN
                    EXECUTE FORMAT('
                        SELECT
                            ov.id,
                            ov.op_type_id,
                            ov.block_num,
                            ov.timestamp,
                            ov.trx_in_block,
                            tv.trx_hash,
                            ov.body::json
                        FROM hive.operations_view ov
                        LEFT JOIN hive.transactions_view tv
                            ON tv.block_num = ov.block_num
                            AND tv.trx_in_block = ov.trx_in_block
                        WHERE ov.block_num >= $1
                            AND ov.block_num <= $2
                            AND ov.op_type_id = ANY ($3)
                        ORDER BY ov.block_num, trx_in_block, ov.id;')
                    USING _first_block, _last_block, _op_ids
                LOOP
                    EXECUTE FORMAT('SELECT %s ($1,$2,$3,$4);', (_ops->>(temprow.op_type_id::varchar)))
                        USING temprow.block_num, temprow.timestamp, temprow.trx_hash, temprow.body;
                    _last_block_time := temprow.timestamp;
                END LOOP;
                -- save done as run end
                RAISE NOTICE 'Block range: <%, %> processed successfully.', _first_block, _last_block;
                UPDATE hpp.plug_state
                    SET check_in = (NOW() AT TIME ZONE 'UTC'), latest_block_time = _last_block_time, latest_block_num = _last_block
                    WHERE plug = _plug_name;
                COMMIT;
            END LOOP;
            IF _to_attach = true THEN
                -- attach context
                PERFORM hive.app_context_attach(_app_context, _last_block);
                RAISE NOTICE 'Context attached.';
            END IF;
        END;
    $$;