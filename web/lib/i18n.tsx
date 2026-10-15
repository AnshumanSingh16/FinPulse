"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { setApiLang } from "./api";

export type Lang = "en" | "hi";

/** English → Hindi. Keys are the English text, so untranslated strings simply show in English. */
const HI: Record<string, string> = {
  // ask: the agent
  "Ask FinPilot": "FinPilot से पूछें", "Your shop assistant": "आपकी दुकान का सहायक", "New chat": "नई बातचीत",
  "What can I help with today?": "आज मैं क्या मदद करूँ?",
  "I look through your khata, bank and bills, run the numbers with tested calculations, check every figure, and can prepare entries and reminders for you to confirm.":
    "मैं आपका खाता, बैंक और बिल देखता हूँ, जाँचे-परखे हिसाब से आंकड़े निकालता हूँ, हर आंकड़ा दोबारा जाँचता हूँ, और एंट्री व याद-संदेश आपकी पुष्टि के लिए तैयार कर सकता हूँ।",
  "Plan my day": "आज का काम", "Khata & udhaar": "खाता और उधारी", "Profit & costs": "मुनाफ़ा और खर्च", "What-ifs": "अगर ऐसा हो तो", "Do it for me": "मेरे लिए कर दो",
  "What should I do today?": "आज मुझे क्या करना चाहिए?", "Who owes me money, and who pays late?": "किस पर उधारी बाकी है, और कौन देर से चुकाता है?",
  "Am I making money? Why did costs go up last month?": "क्या मैं मुनाफ़ा कमा रहा हूँ? पिछले महीने खर्च क्यों बढ़ा?",
  "Will I have enough cash for the next 3 months?": "क्या अगले 3 महीने के लिए कैश काफ़ी है?", "Can I raise prices by 5%?": "दाम 5% बढ़ाऊँ तो?", "Add a sale of ₹500 cash": "₹500 की नकद बिक्री जोड़ो",
  "Answers now come from built-in rules": "अभी जवाब बिल्ट-इन नियमों से आ रहे हैं",
  "They work offline for common questions. Turn on the AI agent to ask anything in your own words — it plans, uses 21 tools and checks every figure.":
    "ये आम सवालों के लिए बिना इंटरनेट चलते हैं। अपने शब्दों में कुछ भी पूछने के लिए AI एजेंट चालू करें — वह योजना बनाता है, 21 टूल इस्तेमाल करता है और हर आंकड़ा जाँचता है।",
  "Set up AI": "AI चालू करें", "Turn AI back on": "AI फिर चालू करें", "AI agent": "AI एजेंट", "AI agent on": "AI एजेंट चालू", "Built-in answers": "बिल्ट-इन जवाब",
  "The AI agent is working…": "AI एजेंट काम कर रहा है…", "Working it out…": "हिसाब लगा रहा हूँ…", "Reading your question": "आपका सवाल पढ़ रहा हूँ",
  "Ask anything…": "कुछ भी पूछें…", "Your question": "आपका सवाल", "Speak your question": "बोलकर पूछें", Send: "भेजें",
  "AI agent: your question and the figures its tools work out are sent to Anthropic. Your files are not.": "AI एजेंट: आपका सवाल और टूल से निकले आंकड़े Anthropic को भेजे जाते हैं। आपकी फ़ाइलें नहीं।",
  "Built-in answers: nothing leaves this computer.": "बिल्ट-इन जवाब: कुछ भी इस कंप्यूटर से बाहर नहीं जाता।", "Nothing is saved or sent until you confirm.": "आपकी पुष्टि के बिना कुछ सेव या भेजा नहीं जाता।",
  "{n} steps · how I worked this out": "{n} क़दम · मैंने कैसे निकाला", "{n} checks passed": "{n} जाँच पास",
  "Ready for you to confirm": "आपकी पुष्टि के लिए तैयार", Confirm: "पुष्टि करें", "Not now": "अभी नहीं", "Open WhatsApp": "WhatsApp खोलें",
  "Cancelled — nothing was saved.": "रद्द — कुछ सेव नहीं हुआ।", Clears: "चुकता होगा", "{amt} more than they owe": "बकाया से {amt} ज़्यादा",
  "Save {amt} a month for {m} months": "{m} महीने तक हर महीने {amt} बचाएँ", "Spent so far this month: {amt}": "इस महीने अब तक खर्च: {amt}", "oldest {d} days late": "सबसे पुराना {d} दिन देर",
  "No phone number saved — WhatsApp will ask you to pick the contact.": "फ़ोन नंबर सेव नहीं — WhatsApp में संपर्क चुनना होगा।",
  "Record a sale": "बिक्री दर्ज करें", "Record an expense": "खर्च दर्ज करें", "Give udhaar (sale on credit)": "उधार दें", "Record money received": "मिला पैसा दर्ज करें",
  "Add a supplier bill": "सप्लायर बिल जोड़ें", "Record a payment to a supplier": "सप्लायर को भुगतान दर्ज करें", "Create a savings goal": "बचत का लक्ष्य बनाएँ", "Set a monthly budget": "महीने का बजट तय करें",
  // AI setup
  "The AI agent is on": "AI एजेंट चालू है", "The AI agent is paused": "AI एजेंट रुका हुआ है", "AI agent is on": "AI एजेंट चालू हो गया", "Key removed from this computer": "Key इस कंप्यूटर से हटा दी गई",
  "Key {hint} is saved on this computer only.": "Key {hint} सिर्फ़ इसी कंप्यूटर पर सेव है।", "Using the key from your computer's settings ({hint}).": "आपके कंप्यूटर की सेटिंग वाली key ({hint}) इस्तेमाल हो रही है।",
  "Model: {model}": "मॉडल: {model}", "Pause AI (use built-in answers)": "AI रोकें (बिल्ट-इन जवाब)", "Remove key": "Key हटाएँ",
  "Without AI, Ask uses FinPilot's built-in rules — they work offline and cover common questions. With your own Anthropic API key, an AI agent plans each question, uses 21 tools on your records, checks every figure and can prepare entries, reminders, goals and budgets for you to confirm.":
    "AI के बिना, FinPilot अपने बिल्ट-इन नियमों से जवाब देता है — ये बिना इंटरनेट आम सवालों के लिए चलते हैं। अपनी Anthropic API key से AI एजेंट हर सवाल की योजना बनाता है, आपके हिसाब पर 21 टूल चलाता है, हर आंकड़ा जाँचता है, और एंट्री, याद-संदेश, लक्ष्य व बजट आपकी पुष्टि के लिए तैयार कर सकता है।",
  "Get a key from the Anthropic Console (usage is billed by Anthropic to your account).": "Anthropic Console से key लें (इस्तेमाल का बिल Anthropic आपके खाते में लगाता है)।",
  "Paste it here:": "यहाँ पेस्ट करें:", "Anthropic API key": "Anthropic API key", "I understand what is sent to Anthropic when AI is on.": "मैं समझता हूँ कि AI चालू होने पर Anthropic को क्या भेजा जाता है।",
  "Checking the key…": "Key जाँच रहे हैं…", "Check key and turn on AI": "Key जाँचें और AI चालू करें",
  "The key is checked with a free call and saved in the .env file on this computer — never in the app's code.": "Key एक मुफ़्त कॉल से जाँची जाती है और इसी कंप्यूटर की .env फ़ाइल में सेव होती है — ऐप के कोड में कभी नहीं।",
  "What leaves this computer when AI is on": "AI चालू होने पर क्या बाहर जाता है",
  "Your question and the results of the tools the agent runs — amounts, dates, and customer and supplier names — are sent to Anthropic to write the answer. Your uploaded files and full records are not sent. With AI off, nothing leaves this computer.":
    "आपका सवाल और एजेंट के टूल के नतीजे — रकम, तारीख़ें, और ग्राहकों व सप्लायरों के नाम — जवाब लिखने के लिए Anthropic को भेजे जाते हैं। आपकी अपलोड की गई फ़ाइलें और पूरा हिसाब नहीं भेजा जाता। AI बंद हो तो कुछ भी बाहर नहीं जाता।",
  "On — Ask uses the AI agent with your own Anthropic key.": "चालू — 'पूछें' आपकी अपनी Anthropic key से AI एजेंट इस्तेमाल करता है।",
  "Off — Ask uses built-in answers and nothing leaves this computer.": "बंद — 'पूछें' बिल्ट-इन जवाब देता है और कुछ भी बाहर नहीं जाता।", Manage: "बदलें",
  // theme
  Theme: "थीम", Light: "हल्की", Auto: "अपने आप", Dark: "गहरी",
  // navigation
  Home: "होम", Khata: "खाता", Money: "पैसा", Ask: "पूछें", Plan: "योजना", Calendar: "कैलेंडर", "Goals & budgets": "लक्ष्य और बजट",
  Reports: "रिपोर्ट", "Your data": "आपका डेटा", More: "और", "Health score": "हेल्थ स्कोर", "New entry": "नई एंट्री", Settings: "सेटिंग्स",
  "You're exploring a demo shop with made-up numbers.": "आप नकली आंकड़ों वाली डेमो दुकान देख रहे हैं।",
  "Switch to my business": "मेरे कारोबार पर जाएँ", "Add my own data": "अपना डेटा जोड़ें",
  "Figures up to {date}": "{date} तक के आंकड़े",
  // greetings & home
  "Good morning": "सुप्रभात", "Good afternoon": "नमस्ते", "Good evening": "शुभ संध्या",
  "Money in the bank today": "आज बैंक में पैसा", "Matches your bank statement": "बैंक स्टेटमेंट से मेल खाता है",
  "Covers {n} months of costs": "{n} महीने का खर्च चल जाएगा", "Expected in 90 days": "90 दिन बाद अनुमान",
  "How do we know?": "हमें कैसे पता?", "Needs your attention": "ध्यान दें", "Show {n} more": "{n} और दिखाएँ",
  "Hide for now": "अभी छिपाएँ", "Added to to-dos": "काम-सूची में जोड़ा",
  "Add sale": "बिक्री", "Add expense": "खर्च", "Gave udhaar": "उधार दिया", "Got payment": "पैसा मिला", "Remind all": "सबको याद दिलाएँ",
  "Your week": "आपका हफ़्ता", "Tap to see your week": "अपना हफ़्ता देखें",
  "Sales received": "बिक्री से आया", "Running costs paid": "खर्च दिया", Profit: "मुनाफ़ा", Loss: "घाटा", "(estimate)": "(अनुमान)",
  "vs {month}": "{month} से तुलना", "Ask FinPilot why": "FinPilot से पूछें क्यों", "How is profit worked out?": "मुनाफ़ा कैसे निकाला?",
  "All months": "सभी महीने", "Where your money went": "पैसा कहाँ गया", "See all payments": "सभी भुगतान देखें",
  "Sales and running costs, month by month": "हर महीने बिक्री और खर्च", "Bills in the next 14 days": "अगले 14 दिन के बिल",
  "Your to-dos": "आपके काम", Done: "हो गया", "Recent entries": "हाल की एंट्री", Undo: "वापस लें", Undone: "वापस लिया",
  "Nothing pending. When you or FinPilot suggest an action — like paying a bill — it lands here for you to approve. FinPilot never pays or sends anything itself.":
    "कुछ बाकी नहीं। जब आप या FinPilot कोई काम सुझाते हैं — जैसे बिल भरना — तो वह मंज़ूरी के लिए यहाँ आता है। FinPilot खुद कुछ नहीं भेजता या चुकाता।",
  "Based on your records up to {date}": "{date} तक के आपके हिसाब के आधार पर",
  "Solid: your actual balance. Dashed: expected — not a guarantee.": "पूरी लाइन: असली बैलेंस। टूटी लाइन: अनुमान — गारंटी नहीं।",
  "Add bank balance": "बैंक बैलेंस जोड़ें",
  "Type in the closing balance from your bank statement or banking app — it takes ten seconds.": "बैंक स्टेटमेंट या बैंकिंग ऐप से आज का बैलेंस डालें — दस सेकंड लगेंगे।",
  // quick entry
  Sale: "बिक्री", Expense: "खर्च", "Udhaar given": "उधार दिया", "Payment received": "पैसा मिला", "Supplier bill": "सप्लायर बिल", "Paid supplier": "सप्लायर को दिया",
  Amount: "रकम", "Customer name": "ग्राहक का नाम", "Supplier name": "सप्लायर का नाम", "Name (optional)": "नाम (वैकल्पिक)", Category: "श्रेणी",
  Cash: "नकद", UPI: "UPI", Bank: "बैंक", Card: "कार्ड", Cheque: "चेक", Date: "तारीख", "Due date": "देय तारीख", Note: "नोट", Save: "सेव करें",
  "Type or speak: “sold masala to Ravi 2500 cash”": "लिखें या बोलें: “Ravi ko 2500 ka maal becha cash”",
  "Fill from text": "टेक्स्ट से भरें", Listening: "सुन रहे हैं", Saved: "सेव हो गया", "Paid with": "भुगतान का तरीका",
  "How will you pay?": "भुगतान कैसे?", "Money comes in": "पैसा आया", "Money goes out": "पैसा गया", "On credit": "उधार पर",
  // khata
  "You'll get": "आपको मिलेंगे", "You'll give": "आपको देने हैं", Customers: "ग्राहक", Suppliers: "सप्लायर", overdue: "बकाया",
  "Pays on time": "समय पर देते हैं", "Sometimes late": "कभी-कभी देर", "Often late": "अक्सर देर", New: "नया",
  "Promised {amt} by {date}": "{date} तक {amt} का वादा", "Promise broken": "वादा टूटा", "Search name": "नाम खोजें",
  "Remind all overdue": "सभी बकाया को याद दिलाएँ", "Settled": "हिसाब साफ़", "Set promise date": "वादे की तारीख", "Phone (WhatsApp)": "फ़ोन (WhatsApp)",
  "Send reminder": "याद दिलाएँ", "Record payment": "पैसा दर्ज करें", "Give udhaar": "उधार दें", "Pay bill": "बिल चुकाएँ", "Add bill": "बिल जोड़ें",
  "Total business": "कुल लेन-देन", "days late": "दिन देर", "Copy message": "मैसेज कॉपी करें", "Open in WhatsApp": "WhatsApp में खोलें", Copied: "कॉपी हुआ",
  "Nothing overdue — great collections!": "कुछ बकाया नहीं — शानदार वसूली!",
  // money
  Transactions: "लेन-देन", "Sort transactions": "श्रेणी चुनें", "Profit by month": "महीने का मुनाफ़ा", "Money in": "आया", "Money out": "गया", All: "सब",
  "All categories": "सभी श्रेणियाँ", "Show more": "और दिखाएँ", "Always use this for {name}": "{name} के लिए हमेशा यही",
  "All sorted! Every transaction has a category.": "सब हो गया! हर लेन-देन की श्रेणी है।", guess: "अंदाज़ा",
  // plan
  "Plan ahead": "आगे की योजना", "Can I afford it?": "क्या मैं ख़रीद सकता हूँ?", "Cash ahead": "आगे का कैश", "Raise prices?": "दाम बढ़ाएँ?",
  "Run a discount?": "छूट दें?", "Hire someone?": "किसी को रखें?", "Take a loan?": "लोन लें?",
  // calendar & goals
  Today: "आज", "GST set-aside": "GST के लिए अलग रखें", Budgets: "बजट", "Savings goals": "बचत लक्ष्य", "Suggest from my spending": "मेरे खर्च से सुझाएँ",
  "Add goal": "लक्ष्य जोड़ें", "Add money": "पैसा जोड़ें",
  // generic
  Back: "वापस", Next: "आगे", Close: "बंद करें", Cancel: "रद्द करें", Delete: "हटाएँ", Loading: "लोड हो रहा है", "Try again": "फिर कोशिश करें",
  "Not financial advice.": "यह वित्तीय सलाह नहीं है।", Language: "भाषा", "since last month": "पिछले महीने से",
  "Ask anything about your business": "अपने कारोबार के बारे में कुछ भी पूछें",
  "Answers come straight from your records, and every figure is double-checked before you see it.": "जवाब सीधे आपके हिसाब से आते हैं, और हर आंकड़ा दिखाने से पहले दोबारा जाँचा जाता है।",
  "Ask about sales, costs, cash, customers, a purchase…": "बिक्री, खर्च, कैश, ग्राहक, किसी ख़रीद के बारे में पूछें…",
  "Every figure checked against your records": "हर आंकड़ा आपके हिसाब से जाँचा गया", "Some figures couldn't be checked": "कुछ आंकड़े जाँचे नहीं जा सके",
  "Built-in answer (no AI)": "बिल्ट-इन जवाब (AI नहीं)", "How I worked this out": "मैंने यह कैसे निकाला",
  "Reading your records": "आपका हिसाब पढ़ रहे हैं", "Running the numbers": "हिसाब लगा रहे हैं", "Double-checking every figure": "हर आंकड़ा जाँच रहे हैं",
  "AI mode: your question and the relevant figures are sent to Anthropic to write the answer. Your files are not.": "AI मोड: जवाब लिखने के लिए आपका सवाल और ज़रूरी आंकड़े Anthropic को भेजे जाते हैं। आपकी फ़ाइलें नहीं।",
  "Offline mode: answers come from FinPilot's built-in rules. Nothing leaves this computer.": "ऑफ़लाइन मोड: जवाब FinPilot के बिल्ट-इन नियमों से। कुछ भी इस कंप्यूटर से बाहर नहीं जाता।",
};

interface LangCtx {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (s: string, vars?: Record<string, string | number>) => string;
}

const Ctx = createContext<LangCtx>({ lang: "en", setLang: () => {}, t: (s) => s });

function fill(s: string, vars?: Record<string, string | number>) {
  if (!vars) return s;
  return s.replace(/\{(\w+)\}/g, (_, k) => (vars[k] != null ? String(vars[k]) : `{${k}}`));
}

export function LangProvider({ children, onChange }: { children: React.ReactNode; onChange?: () => void }) {
  const [lang, setLangState] = useState<Lang>("en");
  useEffect(() => {
    let saved: Lang = "en";
    try {
      saved = (localStorage.getItem("finpilot-lang") as Lang) || "en";
    } catch {}
    setApiLang(saved);
    setLangState(saved);
    document.documentElement.lang = saved === "hi" ? "hi-IN" : "en-IN";
  }, []);
  const setLang = useCallback(
    (l: Lang) => {
      try {
        localStorage.setItem("finpilot-lang", l);
      } catch {}
      setApiLang(l);
      setLangState(l);
      document.documentElement.lang = l === "hi" ? "hi-IN" : "en-IN";
      onChange?.();
    },
    [onChange],
  );
  const t = useCallback((s: string, vars?: Record<string, string | number>) => fill(lang === "hi" ? HI[s] ?? s : s, vars), [lang]);
  return <Ctx.Provider value={{ lang, setLang, t }}>{children}</Ctx.Provider>;
}

export function useT() {
  return useContext(Ctx);
}
