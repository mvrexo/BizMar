-- Run ONCE in Supabase SQL Editor to create a PUBLIC bucket for product images only.
-- Do NOT upload customer documents, payment records or other private files here.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('product-images','product-images',true,5242880,
        array['image/jpeg','image/png','image/webp'])
on conflict (id) do update set public=true, file_size_limit=5242880,
  allowed_mime_types=array['image/jpeg','image/png','image/webp'];
-- No anonymous upload policy: upload occurs only via server-side secret key.
