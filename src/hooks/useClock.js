import { useEffect, useState } from "react";

export function useClock(locale = "pt-BR") {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const formattedDate = time.toLocaleDateString(locale, {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  });

  const formattedTime = time.toLocaleTimeString(locale, {
    hour: "2-digit",
    minute: "2-digit",
  });

  return { time, formattedDate, formattedTime };
}
