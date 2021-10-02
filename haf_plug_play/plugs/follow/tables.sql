CREATE TABLE IF NOT EXISTS public.hpp_follow(
    ppop_id integer NOT NULL UNIQUE,
    block_num integer NOT NULL,
    transaction_id char(40) NOT NULL,
    req_auths text array,
    req_posting_auths text array,
    account varchar(16),
    following varchar(16),
    what text array
);

CREATE INDEX hpp_follow_ix_ppop_id
    ON hpp_follow (ppop_id);

CREATE TABLE IF NOT EXISTS public.hpp_follow_state(
    account varchar(16),
    following varchar(16),
    what text array
);

CREATE INDEX hpp_follow_state_ix_account_following
    ON hpp_follow_state (account, following);

ALTER TABLE public.hpp_follow_state ADD CONSTRAINT "hpp_follow_state_pkey_unique" PRIMARY KEY (account,following);