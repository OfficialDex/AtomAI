import discord
from discord import app_commands
from discord.ext import commands
import requests
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TOKENZ")

API_URL = "https://rudsdev.xyz/api/ai?soru={}"

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

tickets = {}
users = {}
setup_by = {}

class TicketView(discord.ui.View):
    def __init__(self, g_id):
        super().__init__(timeout=None)
        self.g_id = g_id

    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.primary, custom_id="create_ticket")
    async def create_ticket(self, i: discord.Interaction, b: discord.ui.Button):
        g_id = i.guild.id
        if i.user.id in users:
            return await i.response.send_message("⚠️ You already have an open ticket!", ephemeral=True)

        t_set = tickets.get(g_id)
        if not t_set:
            return await i.response.send_message("⚠️ Ticket system is not set up.", ephemeral=True)

        if not i.guild.me.guild_permissions.manage_channels:
            return await i.response.send_message("⚠️ I don't have permission to create channels!", ephemeral=True)

        cat = discord.utils.get(i.guild.categories, name="Tickets")
        if not cat:
            cat = await i.guild.create_category("Tickets")

        t_chan = await i.guild.create_text_channel(f"ticket-{i.user.name}", category=cat)
        await t_chan.set_permissions(i.user, read_messages=True, send_messages=True)

        users[i.user.id] = {"chan_id": t_chan.id, "chat": []}
        await t_chan.send(f"Hello {i.user.mention}, describe your issue.")
        await i.response.send_message(f"✅ Ticket created: {t_chan.mention}", ephemeral=True)

@bot.tree.command(name="setup-ticket", description="Set up the AI ticket system")
@app_commands.describe(channel="Channel for ticket button", server_info="Server details for AI", role="Role for human support")
async def setup_ticket(i: discord.Interaction, channel: discord.TextChannel, server_info: str, role: discord.Role):
    if not i.guild.me.guild_permissions.send_messages or not i.guild.me.guild_permissions.manage_channels:
        return await i.response.send_message("⚠️ I don't have the required permissions to set up the ticket system!", ephemeral=True)

    if not role:
        return await i.response.send_message("⚠️ The provided role does not exist!", ephemeral=True)

    tickets[i.guild.id] = {"c_id": channel.id, "info": server_info, "r_id": role.id}
    setup_by[i.guild.id] = i.user.id

    e = discord.Embed(title="🎫 AI Ticket System", description="Click the button below to create a ticket.", color=discord.Color.blue())
    v = TicketView(i.guild.id)
    await channel.send(embed=e, view=v)
    await i.response.send_message("✅ Ticket system set up!", ephemeral=True)

@bot.event
async def on_message(m):
    if m.author.bot or m.channel.category is None or "ticket-" not in m.channel.name:
        return

    u_id = m.author.id
    g_id = m.guild.id
    t_set = tickets.get(g_id)

    if not t_set or u_id not in users or users[u_id]["chan_id"] != m.channel.id:
        return

    info = t_set["info"]
    r_id = t_set["r_id"]
    chat = users[u_id]["chat"]

    chat.append(f"User: {m.content}")

    meta_prompt = """
    You are an AI assistant strictly limited to answering only questions about this server: {context}
    If the user asks anything unrelated, respond: "I am only allowed to answer questions about this server document."
    
    If the issue is resolved, kindly ask if they want to close the ticket. If they say yes, respond exactly with: 'closed!'
    
    Previous Conversation:
    {memory}

    User: {question}
    AI:
    """.format(context=info, memory="\n".join(chat[-5:]), question=m.content)

    res = requests.get(API_URL.format(meta_prompt))
    ai_msg = res.json().get("cevap", "Error: AI response failed.")

    chat.append(f"AI: {ai_msg}")

    if ai_msg == "closed!":
        await m.channel.send("✅ Ticket closed!")
        del users[u_id]
        await m.channel.delete()
    elif "I am only allowed to answer questions about this server document." in ai_msg or "unable to help" in ai_msg:
        role = discord.utils.get(m.guild.roles, id=r_id)
        if role:
            for member in role.members:
                try:
                    dm_msg = "🔔 **New Support Request**\n👤 User: {}\n📌 Channel: {}\n❓ Issue: {}\n⚠️ AI couldn't resolve it.".format(m.author.name, m.channel.name, m.content)
                    await member.send(dm_msg)
                except:
                    pass
            await m.channel.send("🔔 I have informed human support. Please wait for their response.")
            users[u_id]["stopped"] = True
        else:
            await m.channel.send("⚠️ The support role has been deleted! No human support is available.")
            users[u_id]["stopped"] = True
    elif users.get(u_id, {}).get("stopped"):
        return
    else:
        await m.channel.send(ai_msg)

@bot.event
async def on_guild_role_delete(role):
    g_id = role.guild.id
    t_set = tickets.get(g_id)
    if t_set and t_set["r_id"] == role.id:
        admin_id = setup_by.get(g_id)
        if admin_id:
            admin = discord.utils.get(role.guild.members, id=admin_id)
            if admin:
                try:
                    await admin.send(f"⚠️ The support role `{role.name}` has been deleted. AI ticket bot will not function properly!")
                except:
                    pass

bot.run(TOKEN)
