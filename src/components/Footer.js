// src/components/Footer.js
import React from 'react';

function Footer() {
  return (
    <footer className="bg-blue-600 text-white p-4 text-center text-sm mt-8 w-full">
      <p>
        © 2025 Todos os direitos reservados a{" "}
        <a 
          href="https://facebook.com/prof.gutenbergbarroso" 
          target="_blank" 
          rel="noopener noreferrer" 
          className="text-blue-200 hover:underline"
        >
          Gutenberg Barroso
        </a>
      </p>
    </footer>
  );
}

export default Footer;