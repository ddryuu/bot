import asyncio
import datetime
import logging
from typing import List, Optional, Union

from dateutil.relativedelta import relativedelta
from deepdiff import DeepDiff
from discord import (
    CategoryChannel, Colour, Embed, File, Guild,
    Member, Message, NotFound, RawBulkMessageDeleteEvent,
    RawMessageDeleteEvent, RawMessageUpdateEvent, Role,
    TextChannel, User, VoiceChannel)
from discord.abc import GuildChannel
from discord.ext.commands import Bot

from bot.constants import Channels, Emojis, Icons
from bot.constants import Guild as GuildConstant
from bot.utils.time import humanize


log = logging.getLogger(__name__)

BULLET_POINT = "\u2022"
COLOUR_RED = Colour(0xcd6d6d)
COLOUR_GREEN = Colour(0x68c290)
GUILD_CHANNEL = Union[CategoryChannel, TextChannel, VoiceChannel]

CHANNEL_CHANGES_UNSUPPORTED = ("permissions",)
CHANNEL_CHANGES_SUPPRESSED = ("_overwrites",)
MEMBER_CHANGES_SUPPRESSED = ("activity", "status")
ROLE_CHANGES_UNSUPPORTED = ("colour", "permissions")


class ModLog:
    """
    Logging for server events and staff actions
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self._ignored_deletions = []

        self._cached_deletes = []
        self._cached_edits = []

    def ignore_message_deletion(self, *message_ids: int):
        for message_id in message_ids:
            if message_id not in self._ignored_deletions:
                self._ignored_deletions.append(message_id)

    async def send_log_message(
            self, icon_url: Optional[str], colour: Colour, title: Optional[str], text: str, thumbnail: str = None,
            channel_id: int = Channels.modlog, ping_everyone: bool = False, files: List[File] = None
    ):
        embed = Embed(description=text)

        if title and icon_url:
            embed.set_author(name=title, icon_url=icon_url)

        embed.colour = colour
        embed.timestamp = datetime.datetime.utcnow()

        if thumbnail is not None:
            embed.set_thumbnail(url=thumbnail)

        content = None

        if ping_everyone:
            content = "@everyone"

        await self.bot.get_channel(channel_id).send(content=content, embed=embed, files=files)

    async def on_guild_channel_create(self, channel: GUILD_CHANNEL):
        if channel.guild.id != GuildConstant.id:
            return

        if isinstance(channel, CategoryChannel):
            title = "Category created"
            message = f"{channel.name} (`{channel.id}`)"
        elif isinstance(channel, VoiceChannel):
            title = "Voice channel created"

            if channel.category:
                message = f"{channel.category}/{channel.name} (`{channel.id}`)"
            else:
                message = f"{channel.name} (`{channel.id}`)"
        else:
            title = "Text channel created"

            if channel.category:
                message = f"{channel.category}/{channel.name} (`{channel.id}`)"
            else:
                message = f"{channel.name} (`{channel.id}`)"

        await self.send_log_message(Icons.hash_green, COLOUR_GREEN, title, message)

    async def on_guild_channel_delete(self, channel: GUILD_CHANNEL):
        if channel.guild.id != GuildConstant.id:
            return

        if isinstance(channel, CategoryChannel):
            title = "Category deleted"
        elif isinstance(channel, VoiceChannel):
            title = "Voice channel deleted"
        else:
            title = "Text channel deleted"

        if channel.category and not isinstance(channel, CategoryChannel):
            message = f"{channel.category}/{channel.name} (`{channel.id}`)"
        else:
            message = f"{channel.name} (`{channel.id}`)"

        await self.send_log_message(
            Icons.hash_red, COLOUR_RED,
            title, message
        )

    async def on_guild_channel_update(self, before: GUILD_CHANNEL, after: GuildChannel):
        if before.guild.id != GuildConstant.id:
            return

        diff = DeepDiff(before, after)
        changes = []
        done = []

        diff_values = diff.get("values_changed", {})
        diff_values.update(diff.get("type_changes", {}))

        for key, value in diff_values.items():
            if not key:  # Not sure why, but it happens
                continue

            key = key[5:]  # Remove "root." prefix

            if "[" in key:
                key = key.split("[", 1)[0]

            if "." in key:
                key = key.split(".", 1)[0]

            if key in done or key in CHANNEL_CHANGES_SUPPRESSED:
                continue

            if key in CHANNEL_CHANGES_UNSUPPORTED:
                changes.append(f"{key.title()} updated")
            else:
                new = value["new_value"]
                old = value["old_value"]

                changes.append(f"{key.title()}: `{old}` -> `{new}`")

            done.append(key)

        if not changes:
            return

        message = ""

        for item in sorted(changes):
            message += f"{BULLET_POINT} {item}\n"

        if after.category:
            message = f"**{after.category}/#{after.name} (`{after.id}`)**\n{message}"
        else:
            message = f"**#{after.name} (`{after.id}`)**\n{message}"

        await self.send_log_message(
            Icons.hash_blurple, Colour.blurple(),
            "Channel updated", message
        )

    async def on_guild_role_create(self, role: Role):
        if role.guild.id != GuildConstant.id:
            return

        await self.send_log_message(
            Icons.crown_green, COLOUR_GREEN,
            "Role created", f"`{role.id}`"
        )

    async def on_guild_role_delete(self, role: Role):
        if role.guild.id != GuildConstant.id:
            return

        await self.send_log_message(
            Icons.crown_red, COLOUR_RED,
            "Role removed", f"{role.name} (`{role.id}`)"
        )

    async def on_guild_role_update(self, before: Role, after: Role):
        if before.guild.id != GuildConstant.id:
            return

        diff = DeepDiff(before, after)
        changes = []
        done = []

        diff_values = diff.get("values_changed", {})
        diff_values.update(diff.get("type_changes", {}))

        for key, value in diff_values.items():
            if not key:  # Not sure why, but it happens
                continue

            key = key[5:]  # Remove "root." prefix

            if "[" in key:
                key = key.split("[", 1)[0]

            if "." in key:
                key = key.split(".", 1)[0]

            if key in done or key == "color":
                continue

            if key in ROLE_CHANGES_UNSUPPORTED:
                changes.append(f"{key.title()} updated")
            else:
                new = value["new_value"]
                old = value["old_value"]

                changes.append(f"{key.title()}: `{old}` -> `{new}`")

            done.append(key)

        if not changes:
            return

        message = ""

        for item in sorted(changes):
            message += f"{BULLET_POINT} {item}\n"

        message = f"**{after.name} (`{after.id}`)**\n{message}"

        await self.send_log_message(
            Icons.crown_blurple, Colour.blurple(),
            "Role updated", message
        )

    async def on_guild_update(self, before: Guild, after: Guild):
        if before.id != GuildConstant.id:
            return

        diff = DeepDiff(before, after)
        changes = []
        done = []

        diff_values = diff.get("values_changed", {})
        diff_values.update(diff.get("type_changes", {}))

        for key, value in diff_values.items():
            if not key:  # Not sure why, but it happens
                continue

            key = key[5:]  # Remove "root." prefix

            if "[" in key:
                key = key.split("[", 1)[0]

            if "." in key:
                key = key.split(".", 1)[0]

            if key in done:
                continue

            new = value["new_value"]
            old = value["old_value"]

            changes.append(f"{key.title()}: `{old}` -> `{new}`")

            done.append(key)

        if not changes:
            return

        message = ""

        for item in sorted(changes):
            message += f"{BULLET_POINT} {item}\n"

        message = f"**{after.name} (`{after.id}`)**\n{message}"

        await self.send_log_message(
            Icons.guild_update, Colour.blurple(),
            "Guild updated", message,
            thumbnail=after.icon_url_as(format="png")
        )

    async def on_member_ban(self, guild: Guild, member: Union[Member, User]):
        if guild.id != GuildConstant.id:
            return

        await self.send_log_message(
            Icons.user_ban, COLOUR_RED,
            "User banned", f"{member.name}#{member.discriminator} (`{member.id}`)",
            thumbnail=member.avatar_url_as(static_format="png")
        )

    async def on_member_join(self, member: Member):
        if member.guild.id != GuildConstant.id:
            return

        message = f"{member.name}#{member.discriminator} (`{member.id}`)"

        now = datetime.datetime.utcnow()
        difference = abs(relativedelta(now, member.created_at))

        message += "\n\n**Account age:** " + humanize(difference)

        if difference.days < 1 and difference.months < 1 and difference.years < 1:  # New user account!
            message = f"{Emojis.new} {message}"

        await self.send_log_message(
            Icons.sign_in, COLOUR_GREEN,
            "User joined", message,
            thumbnail=member.avatar_url_as(static_format="png")
        )

    async def on_member_remove(self, member: Member):
        if member.guild.id != GuildConstant.id:
            return

        await self.send_log_message(
            Icons.sign_out, COLOUR_RED,
            "User left", f"{member.name}#{member.discriminator} (`{member.id}`)",
            thumbnail=member.avatar_url_as(static_format="png")
        )

    async def on_member_unban(self, guild: Guild, member: User):
        if guild.id != GuildConstant.id:
            return

        await self.send_log_message(
            Icons.user_unban, Colour.blurple(),
            "User unbanned", f"{member.name}#{member.discriminator} (`{member.id}`)",
            thumbnail=member.avatar_url_as(static_format="png")
        )

    async def on_member_update(self, before: Member, after: Member):
        if before.guild.id != GuildConstant.id:
            return

        diff = DeepDiff(before, after)
        changes = []
        done = []

        diff_values = diff.get("values_changed", {})
        diff_values.update(diff.get("type_changes", {}))
        diff_values.update(diff.get("iterable_item_removed", {}))
        diff_values.update(diff.get("iterable_item_added", {}))

        for key, value in diff_values.items():
            if not key:  # Not sure why, but it happens
                continue

            key = key[5:]  # Remove "root." prefix

            if "[" in key:
                key = key.split("[", 1)[0]

            if "." in key:
                key = key.split(".", 1)[0]

            if key in done or key in MEMBER_CHANGES_SUPPRESSED:
                continue

            if key == "roles":
                new_roles = after.roles
                old_roles = before.roles

                for role in old_roles:
                    if role not in new_roles:
                        changes.append(f"Role removed: {role.name} (`{role.id}`)")

                for role in new_roles:
                    if role not in old_roles:
                        changes.append(f"Role added: {role.name} (`{role.id}`)")

            else:
                new = value["new_value"]
                old = value["old_value"]

                changes.append(f"{key.title()}: `{old}` -> `{new}`")

            done.append(key)

        if not changes:
            return

        message = ""

        for item in sorted(changes):
            message += f"{BULLET_POINT} {item}\n"

        message = f"**{after.name}#{after.discriminator} (`{after.id}`)**\n{message}"

        await self.send_log_message(
            Icons.user_update, Colour.blurple(),
            "Member updated", message,
            thumbnail=after.avatar_url_as(static_format="png")
        )

    async def on_raw_bulk_message_delete(self, event: RawBulkMessageDeleteEvent):
        if event.guild_id != GuildConstant.id or event.channel_id in GuildConstant.ignored:
            return

        # Could upload the log to the site - maybe we should store all the messages somewhere?
        # Currently if messages aren't in the cache, we ain't gonna have 'em.

        ignored_messages = 0

        for message_id in event.message_ids:
            if message_id in self._ignored_deletions:
                self._ignored_deletions.remove(message_id)
                ignored_messages += 1

        if ignored_messages >= len(event.message_ids):
            return

        channel = self.bot.get_channel(event.channel_id)

        if channel.category:
            message = f"{len(event.message_ids)} deleted in {channel.category}/#{channel.name} (`{channel.id}`)"
        else:
            message = f"{len(event.message_ids)} deleted in #{channel.name} (`{channel.id}`)"

        await self.send_log_message(
            Icons.message_bulk_delete, Colour.orange(),
            "Bulk message delete",
            message, channel_id=Channels.devalerts,
            ping_everyone=True
        )

    async def on_message_delete(self, message: Message):
        channel = message.channel
        author = message.author

        if message.guild.id != GuildConstant.id or channel.id in GuildConstant.ignored:
            return

        self._cached_deletes.append(message.id)

        if message.id in self._ignored_deletions:
            self._ignored_deletions.remove(message.id)
            return

        if author.bot:
            return

        if channel.category:
            response = (
                f"**Author:** {author.name}#{author.discriminator} (`{author.id}`)\n"
                f"**Channel:** {channel.category}/#{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{message.id}`\n"
                "\n"
                f"{message.clean_content}"
            )
        else:
            response = (
                f"**Author:** {author.name}#{author.discriminator} (`{author.id}`)\n"
                f"**Channel:** #{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{message.id}`\n"
                "\n"
                f"{message.clean_content}"
            )

        if message.attachments:
            # Prepend the message metadata with the number of attachments
            response = f"**Attachments:** {len(message.attachments)}\n" + response

        await self.send_log_message(
            Icons.message_delete, COLOUR_RED,
            "Message deleted",
            response,
            channel_id=Channels.message_log
        )

    async def on_raw_message_delete(self, event: RawMessageDeleteEvent):
        if event.guild_id != GuildConstant.id or event.channel_id in GuildConstant.ignored:
            return

        await asyncio.sleep(1)  # Wait here in case the normal event was fired

        if event.message_id in self._cached_deletes:
            # It was in the cache and the normal event was fired, so we can just ignore it
            self._cached_deletes.remove(event.message_id)
            return

        if event.message_id in self._ignored_deletions:
            self._ignored_deletions.remove(event.message_id)
            return

        channel = self.bot.get_channel(event.channel_id)

        if channel.category:
            response = (
                f"**Channel:** {channel.category}/#{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{event.message_id}`\n"
                "\n"
                "This message was not cached, so the message content cannot be displayed."
            )
        else:
            response = (
                f"**Channel:** #{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{event.message_id}`\n"
                "\n"
                "This message was not cached, so the message content cannot be displayed."
            )

        await self.send_log_message(
            Icons.message_delete, COLOUR_RED,
            "Message deleted",
            response,
            channel_id=Channels.message_log
        )

    async def on_message_edit(self, before: Message, after: Message):
        if before.guild.id != GuildConstant.id or before.channel.id in GuildConstant.ignored or before.author.bot:
            return

        self._cached_edits.append(before.id)

        if before.content == after.content:
            return

        author = before.author
        channel = before.channel

        if channel.category:
            before_response = (
                f"**Author:** {author.name}#{author.discriminator} (`{author.id}`)\n"
                f"**Channel:** {channel.category}/#{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{before.id}`\n"
                "\n"
                f"{before.clean_content}"
            )

            after_response = (
                f"**Author:** {author.name}#{author.discriminator} (`{author.id}`)\n"
                f"**Channel:** {channel.category}/#{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{before.id}`\n"
                "\n"
                f"{after.clean_content}"
            )
        else:
            before_response = (
                f"**Author:** {author.name}#{author.discriminator} (`{author.id}`)\n"
                f"**Channel:** #{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{before.id}`\n"
                "\n"
                f"{before.clean_content}"
            )

            after_response = (
                f"**Author:** {author.name}#{author.discriminator} (`{author.id}`)\n"
                f"**Channel:** #{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{before.id}`\n"
                "\n"
                f"{after.clean_content}"
            )

        await self.send_log_message(
            Icons.message_edit, Colour.blurple(), "Message edited (Before)",
            before_response, channel_id=Channels.message_log
        )

        await self.send_log_message(
            Icons.message_edit, Colour.blurple(), "Message edited (After)",
            after_response, channel_id=Channels.message_log
        )

    async def on_raw_message_edit(self, event: RawMessageUpdateEvent):
        try:
            channel = self.bot.get_channel(int(event.data["channel_id"]))
            message = await channel.get_message(event.message_id)
        except NotFound:  # Was deleted before we got the event
            return

        if message.guild.id != GuildConstant.id or message.channel.id in GuildConstant.ignored or message.author.bot:
            return

        await asyncio.sleep(1)  # Wait here in case the normal event was fired

        if event.message_id in self._cached_edits:
            # It was in the cache and the normal event was fired, so we can just ignore it
            self._cached_edits.remove(event.message_id)
            return

        author = message.author
        channel = message.channel

        if channel.category:
            before_response = (
                f"**Author:** {author.name}#{author.discriminator} (`{author.id}`)\n"
                f"**Channel:** {channel.category}/#{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{message.id}`\n"
                "\n"
                "This message was not cached, so the message content cannot be displayed."
            )

            after_response = (
                f"**Author:** {author.name}#{author.discriminator} (`{author.id}`)\n"
                f"**Channel:** {channel.category}/#{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{message.id}`\n"
                "\n"
                f"{message.clean_content}"
            )
        else:
            before_response = (
                f"**Author:** {author.name}#{author.discriminator} (`{author.id}`)\n"
                f"**Channel:** #{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{message.id}`\n"
                "\n"
                "This message was not cached, so the message content cannot be displayed."
            )

            after_response = (
                f"**Author:** {author.name}#{author.discriminator} (`{author.id}`)\n"
                f"**Channel:** #{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{message.id}`\n"
                "\n"
                f"{message.clean_content}"
            )

        await self.send_log_message(
            Icons.message_edit, Colour.blurple(), "Message edited (Before)",
            before_response, channel_id=Channels.message_log
        )

        await self.send_log_message(
            Icons.message_edit, Colour.blurple(), "Message edited (After)",
            after_response, channel_id=Channels.message_log
        )


def setup(bot):
    bot.add_cog(ModLog(bot))
    log.info("Cog loaded: ModLog")