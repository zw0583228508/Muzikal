import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en";
import he from "./he";

i18n
  .use(initReactI18next)
  .init({
    resources: {
      en,
      he
    },
    lng: "en", // default language
    fallbackLng: "en",
    interpolation: {
      escapeValue: false
    }
  });

i18n.on('languageChanged', (lng) => {
  document.documentElement.dir = lng === 'he' ? 'rtl' : 'ltr';
});

export default i18n;
