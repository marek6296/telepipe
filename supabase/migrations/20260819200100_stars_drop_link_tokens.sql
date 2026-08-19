-- `star_link_tokens` bola postavená na predpoklade, že klient musí najprv
-- spustiť bota cez deep link a až potom dostane faktúru.
--
-- `createInvoiceLink` ten krok celý ruší: web si vypýta odkaz na faktúru
-- a klient naň len klikne — otvorí sa mu rovno platobné okno v Telegrame, aj
-- keby bota nikdy nespustil. Payload faktúry (1–128 B, používateľ ho nevidí)
-- si nesie `account_id` sám, takže párovací token nemá čo riešiť.
--
-- Mŕtva tabuľka by len zvádzala k tomu, aby ju niekto raz začal používať.

drop table if exists star_link_tokens;
