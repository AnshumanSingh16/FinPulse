# Munshi — the AI bookkeeper that lives in a chat

## The problem
Crores of Indian shopkeepers, kirana owners, wholesalers and small manufacturers run their business from memory, a notebook and WhatsApp. They don't lack data — every UPI payment and udhaar is somewhere — they lack someone to **keep the books and tell them what to do**. Accounting apps give them forms, dashboards and reports they never open.

Big businesses have a *munshi* (or an accountant) for this. Small ones can't afford one.

## The product
**Munshi is that person, in a chat.** One screen that looks and feels like WhatsApp:

- **You talk, Munshi writes it down.** *“Ravi ko 2500 udhaar”*, *“Metro ne 50k diye”*, *“bijli ka bill 3200 diya”* — typed or spoken, in Hindi, English or Hinglish. Munshi prepares the entry; one tap saves it.
- **The chat is the khata.** Every entry, payment and reminder appears in the thread, with Undo. Scroll up and you're reading your account book.
- **Munshi speaks first.** Each morning it posts one message: what needs you today (who to collect from, which bills are due, anything odd), with the actions already prepared.
- **Lena / Dena, always visible.** Bank balance, money to collect, money to pay — one strip at the top.
- **Ask anything.** *“Is mahine kaisa raha?”*, *“kaun der se deta hai?”*, *“₹12 lakh ki machine le sakta hoon?”* — answered from your own records.
- **The Khata screen** — every customer and supplier, what they owe, and a WhatsApp reminder in one tap.

## Principles
1. **One screen.** If it can be a message, it is a message. No dashboards to learn.
2. **Never invent a number.** Every figure comes from tested Python calculations over the owner's records and is checked before it is shown. If the data can't answer, Munshi says so.
3. **Prepare, never act alone.** Munshi drafts; the owner taps. It never pays, sends or files anything itself.
4. **Speak like the owner.** Hindi, English, Hinglish, voice. Lakh and crore. Udhaar, lena, dena.
5. **Works offline first.** Built-in answers need no internet or AI key; an AI key (Gemini free tier or Claude) makes Munshi understand anything.
6. **The owner's data stays on their machine** unless they turn AI on — and then only the figures needed to answer.

## Who it's for (first)
A shop or small trading/manufacturing business in India with 10–200 customers on udhaar, a bank account with UPI, and an owner who lives on WhatsApp.

## What we deliberately left out
Health scores, weekly stories, calendars, simulator pages, budgets screens and charts dashboards. The engine behind them still exists and Munshi uses it when asked — but none of it is a screen to learn.

## Next
1. Real WhatsApp: receive messages and send reminders from the owner's own WhatsApp Business number (with approval).
2. Bank statement and UPI SMS import that runs by itself.
3. Multi-device (owner + staff), with the books in the cloud under the owner's control.
4. GST-ready monthly pack for the CA, generated in the chat.
