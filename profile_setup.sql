-- Run once in Supabase SQL Editor.
-- Keep the service-role key on the Streamlit server only.
create table if not exists public.owner_profiles (
  email text primary key,
  display_name text not null default 'Owner',
  business_name text not null default 'Nour Sweets',
  phone text not null default '',
  avatar_path text,
  updated_at timestamptz not null default now()
);
alter table public.owner_profiles enable row level security;
-- No anon/authenticated policies: app uses server-side service role after owner verification.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('owner-avatars', 'owner-avatars', false, 3145728, array['image/jpeg','image/png','image/webp'])
on conflict (id) do update set public = false, file_size_limit = 3145728,
allowed_mime_types = array['image/jpeg','image/png','image/webp'];
