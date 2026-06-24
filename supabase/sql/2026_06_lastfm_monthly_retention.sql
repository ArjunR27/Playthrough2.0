-- Monthly Last.fm retention for Playthrough.
-- Run this in the Supabase SQL editor before enabling the cron cleanup.

create table if not exists public.maintenance_state (
    state_key text primary key,
    state_value text not null,
    updated_at timestamptz not null default now()
);

create index if not exists idx_last_fm_listened_tracks_played_at
    on public.last_fm_listened_tracks (played_at);

create index if not exists idx_last_fm_listened_tracks_album_key
    on public.last_fm_listened_tracks (album_key);

create index if not exists idx_wall_items_provider_album_id
    on public.wall_items (provider, album_id);

drop function if exists public.get_last_fm_album_completion(text);
drop function if exists public.get_last_fm_album_tracks(text, text);

create or replace function public.get_last_fm_album_completion(p_lastfm_username text)
returns table (
    album_key text,
    album_name text,
    primary_artist text,
    listened bigint,
    total integer,
    album_image text
)
language sql
stable
as $$
    with bounds as (
        select (date_trunc('month', now() at time zone 'UTC') at time zone 'UTC') as month_start
    ),
    current_listens as (
        select distinct
            l.album_key,
            l.track_name_normalized
        from public.last_fm_listened_tracks l
        cross join bounds b
        where l.lastfm_username = p_lastfm_username
          and l.played_at >= b.month_start
          and l.album_key is not null
          and l.track_name_normalized is not null
    ),
    current_albums as (
        select distinct album_key
        from current_listens
    )
    select
        a.album_key::text,
        a.album_name::text,
        a.artist_name::text as primary_artist,
        count(distinct t.track_number) filter (
            where cl.track_name_normalized is not null
        )::bigint as listened,
        coalesce(nullif(a.total_tracks, 0), count(t.track_number)::integer) as total,
        coalesce(a.image_mega, a.image_extralarge, a.image_large)::text as album_image
    from current_albums ca
    join public.last_fm_albums a
      on a.album_key = ca.album_key
    left join public.last_fm_album_tracks t
      on t.album_key = a.album_key
    left join current_listens cl
      on cl.album_key = t.album_key
     and cl.track_name_normalized = t.track_name_normalized
    group by
        a.album_key,
        a.album_name,
        a.artist_name,
        a.total_tracks,
        a.image_mega,
        a.image_extralarge,
        a.image_large
    having coalesce(nullif(a.total_tracks, 0), count(t.track_number)::integer) >= 1
    order by listened desc, a.album_name asc;
$$;

create or replace function public.get_last_fm_album_tracks(
    p_lastfm_username text,
    p_album_key text
)
returns table (
    track_number integer,
    track_name text,
    is_listened boolean
)
language sql
stable
as $$
    with bounds as (
        select (date_trunc('month', now() at time zone 'UTC') at time zone 'UTC') as month_start
    ),
    current_listens as (
        select distinct l.track_name_normalized
        from public.last_fm_listened_tracks l
        cross join bounds b
        where l.lastfm_username = p_lastfm_username
          and l.album_key = p_album_key
          and l.played_at >= b.month_start
          and l.track_name_normalized is not null
    )
    select
        t.track_number::integer,
        t.track_name::text,
        exists (
            select 1
            from current_listens cl
            where cl.track_name_normalized = t.track_name_normalized
        ) as is_listened
    from public.last_fm_album_tracks t
    where t.album_key = p_album_key
    order by t.track_number;
$$;

create or replace function public.run_lastfm_monthly_retention(
    p_month_key text default to_char(now() at time zone 'UTC', 'YYYY-MM'),
    p_dry_run boolean default false
)
returns table (
    table_name text,
    action text,
    row_count bigint
)
language plpgsql
security definer
set search_path = public
as $$
declare
    v_month_start timestamptz;
    v_previous_month text;
    v_count bigint;
begin
    v_month_start := (to_date(p_month_key || '-01', 'YYYY-MM-DD')::timestamp at time zone 'UTC');

    select state_value
      into v_previous_month
      from public.maintenance_state
     where state_key = 'lastfm_monthly_retention_month';

    if not p_dry_run and v_previous_month = p_month_key then
        table_name := 'maintenance_state';
        action := 'skipped_current_month';
        row_count := 0;
        return next;
        return;
    end if;

    create temp table retained_lastfm_album_keys (
        album_key text primary key
    ) on commit drop;

    insert into retained_lastfm_album_keys (album_key)
    select album_key
      from (
          select distinct l.album_key
            from public.last_fm_listened_tracks l
           where l.played_at >= v_month_start
             and l.album_key is not null
          union
          select distinct wi.album_id
            from public.wall_items wi
           where wi.provider = 'lastfm'
             and wi.album_id is not null
      ) retained
    on conflict do nothing;

    if p_dry_run then
        select count(*)
          into v_count
          from public.last_fm_listened_tracks
         where played_at < v_month_start;
        table_name := 'last_fm_listened_tracks';
        action := 'would_delete_before_month';
        row_count := v_count;
        return next;

        select count(*) into v_count from public.last_fm_track_artists;
        table_name := 'last_fm_track_artists';
        action := 'would_truncate';
        row_count := v_count;
        return next;

        select count(*)
          into v_count
          from public.last_fm_album_tracks t
         where not exists (
             select 1
               from retained_lastfm_album_keys r
              where r.album_key = t.album_key
         );
        table_name := 'last_fm_album_tracks';
        action := 'would_delete_orphans';
        row_count := v_count;
        return next;

        select count(*)
          into v_count
          from public.last_fm_albums a
         where not exists (
             select 1
               from retained_lastfm_album_keys r
              where r.album_key = a.album_key
         );
        table_name := 'last_fm_albums';
        action := 'would_delete_orphans';
        row_count := v_count;
        return next;

        select count(*) into v_count from public.last_fm_artists;
        table_name := 'last_fm_artists';
        action := 'would_truncate';
        row_count := v_count;
        return next;

        return;
    end if;

    delete from public.last_fm_listened_tracks
     where played_at < v_month_start;
    get diagnostics v_count = row_count;
    table_name := 'last_fm_listened_tracks';
    action := 'deleted_before_month';
    row_count := v_count;
    return next;

    delete from public.last_fm_track_artists;
    get diagnostics v_count = row_count;
    table_name := 'last_fm_track_artists';
    action := 'truncated';
    row_count := v_count;
    return next;

    delete from public.last_fm_album_tracks t
     where not exists (
         select 1
           from retained_lastfm_album_keys r
          where r.album_key = t.album_key
     );
    get diagnostics v_count = row_count;
    table_name := 'last_fm_album_tracks';
    action := 'deleted_orphans';
    row_count := v_count;
    return next;

    delete from public.last_fm_albums a
     where not exists (
         select 1
           from retained_lastfm_album_keys r
          where r.album_key = a.album_key
     );
    get diagnostics v_count = row_count;
    table_name := 'last_fm_albums';
    action := 'deleted_orphans';
    row_count := v_count;
    return next;

    delete from public.last_fm_artists;
    get diagnostics v_count = row_count;
    table_name := 'last_fm_artists';
    action := 'truncated';
    row_count := v_count;
    return next;

    insert into public.maintenance_state (state_key, state_value, updated_at)
    values ('lastfm_monthly_retention_month', p_month_key, now())
    on conflict (state_key) do update
        set state_value = excluded.state_value,
            updated_at = excluded.updated_at;

    table_name := 'maintenance_state';
    action := 'updated';
    row_count := 1;
    return next;
end;
$$;

grant execute on function public.get_last_fm_album_completion(text) to anon, authenticated, service_role;
grant execute on function public.get_last_fm_album_tracks(text, text) to anon, authenticated, service_role;
grant execute on function public.run_lastfm_monthly_retention(text, boolean) to service_role;
