"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { setApiLang } from "./api";

export type Lang = "en" | "hi";

/** English → Hindi. Keys are the English text, so untranslated strings simply show in English. */
const HI: Record<string, string> = {
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
