"""Long Discord replies: native short-message splitting, full Markdown for overflow.

Patch the pinned adapter without changing recipients, authentication or input gates.
Files are built in memory from the response itself, never from a model-supplied path.
"""
import io,re
from contextlib import closing

INLINE_UNITS=6000
MAX_REPORT_BYTES=5*1024*1024

def units(text):return len(text.encode('utf-16-le'))//2

def clip(text,limit):return text.encode('utf-16-le')[:max(0,limit)*2].decode('utf-16-le',errors='ignore')

def caption(content):
    # Broker-generated task footer is kept at the bottom of the visible preview.
    match=re.search(r'(?m)^Paperclip report(?: KRI-\d+)?: https://paperclip\.example\.invalid/KRI/issues/KRI-\d+\s*(?:\nPaperclip report KRI-\d+: https://paperclip\.example\.invalid/KRI/issues/KRI-\d+\s*)*\Z',content)
    footer=match.group().strip() if match else ''
    body=content[:match.start()] if match else content
    heading='Full reply attached as **report.md**. Preview:\n\n'
    # Many-task batches keep the full list in the attachment; one canonical link remains visible.
    if units(footer)>900:footer=footer.splitlines()[0]+'\nAdditional report links are in report.md.'
    preview=clip(body.strip(),1800-units(heading)-units(footer)-5).rstrip()+'…'
    # Avoid leaving a preview code fence open over the report link.
    preview=preview.replace('```','')
    return heading+preview+('\n\n'+footer if footer else '')

def patch_delivery(cls):
    original_send=cls.send;original_edit=cls.edit_message
    if getattr(original_send,'_hq_reports',False):return

    def long_reply(adapter,content):
        formatted=adapter.format_message(content)
        # Formatting/code fences can increase chunks even below the character threshold.
        return units(formatted)>INLINE_UNITS or len(adapter.truncate_message(formatted,adapter.MAX_MESSAGE_LENGTH))>3

    async def deliver(adapter,chat_id,content,reply_to=None,metadata=None,message_id=None):
        import discord
        from gateway.platforms.base import SendResult
        if not adapter._client:return SendResult(success=False,error='send_path_degraded',retryable=True)
        try:
            data=content.encode('utf-8')
            if len(data)>MAX_REPORT_BYTES:
                return SendResult(success=False,error='Reply exceeds the 5 MiB report limit; request a narrower report.')
            target=str((metadata or {}).get('thread_id') or chat_id)
            channel=await adapter._resolve_channel(target)
            if channel is None:return SendResult(success=False,error='Report destination unavailable')
            with closing(discord.File(io.BytesIO(data),filename='report.md')) as file:
                text=caption(content)
                if message_id:
                    msg=channel.get_partial_message(int(message_id))
                    await msg.edit(content=text,attachments=[file],allowed_mentions=discord.AllowedMentions.none())
                    result=SendResult(success=True,message_id=str(message_id))
                elif adapter._is_forum_parent(channel):
                    result=await adapter._forum_post_file(channel,content=text,file=file)
                else:
                    reference=adapter._reply_reference_for_send(reply_to,channel)
                    try:
                        msg=await channel.send(content=text,file=file,reference=reference,allowed_mentions=discord.AllowedMentions.none())
                    except Exception as error:
                        if reference is None or not adapter._is_reply_reference_rejected(error):raise
                        file.reset()
                        msg=await channel.send(content=text,file=file,reference=None,allowed_mentions=discord.AllowedMentions.none())
                    result=SendResult(success=True,message_id=str(msg.id),raw_response={'message_ids':[str(msg.id)]})
                if result.success and result.message_id:adapter._last_self_message_id[target]=result.message_id
        except Exception:
            # Ambiguous upload failures must not trigger an automatic second send.
            result=SendResult(success=False,error='Report attachment delivery failed; delivery may be uncertain. Check the channel before retrying.')
        if message_id:return result
        return await adapter._record_response_async(reply_to,result,content,bool(metadata and metadata.get('notify')),metadata)

    async def send(self,chat_id,content,reply_to=None,metadata=None):
        if long_reply(self,content):return await deliver(self,chat_id,content,reply_to,metadata)
        return await original_send(self,chat_id,content,reply_to=reply_to,metadata=metadata)

    async def edit(self,chat_id,message_id,content,*,finalize=False,metadata=None):
        if finalize and long_reply(self,content):
            result=await deliver(self,chat_id,content,metadata=metadata,message_id=message_id)
            if result.success:self._last_overflow_preview.pop((str(chat_id),str(message_id)),None)
            return result
        return await original_edit(self,chat_id,message_id,content,finalize=finalize,metadata=metadata)

    send._hq_reports=True
    cls.send=send;cls.edit_message=edit
