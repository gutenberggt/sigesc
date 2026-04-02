import { createContext, useContext, useState, useCallback } from 'react';

const MessagingContext = createContext(null);

export const MessagingProvider = ({ children }) => {
  const [activeChat, setActiveChat] = useState(null);

  const openChat = useCallback((connection) => {
    setActiveChat(connection);
  }, []);

  const closeChat = useCallback(() => {
    setActiveChat(null);
  }, []);

  return (
    <MessagingContext.Provider value={{ activeChat, openChat, closeChat }}>
      {children}
    </MessagingContext.Provider>
  );
};

export const useMessaging = () => {
  const context = useContext(MessagingContext);
  if (!context) {
    throw new Error('useMessaging must be used within a MessagingProvider');
  }
  return context;
};
