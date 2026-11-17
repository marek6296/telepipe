-- Telegram voice notes retain OGG/Opus; web/Fanvue previews use MP3.
-- Keep this bucket private and preserve every existing allowed content type.
update storage.buckets
set allowed_mime_types=array_append(allowed_mime_types,'audio/ogg')
where id='social-media' and allowed_mime_types is not null
  and not ('audio/ogg'=any(allowed_mime_types));
