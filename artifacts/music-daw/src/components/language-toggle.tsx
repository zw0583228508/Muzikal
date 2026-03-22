import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";

export function LanguageToggle() {
  const { i18n } = useTranslation();

  const toggleLanguage = () => {
    const nextLang = i18n.language === 'en' ? 'he' : 'en';
    i18n.changeLanguage(nextLang);
  };

  return (
    <Button variant="outline" size="sm" onClick={toggleLanguage} className="font-display">
      {i18n.language === 'en' ? 'עב' : 'EN'}
    </Button>
  );
}
