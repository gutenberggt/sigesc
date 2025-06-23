// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { getAuth } from 'firebase/auth';
// TODO: Add SDKs for Firebase products that you want to use
// https://firebase.google.com/docs/web/setup#available-libraries

// Your web app's Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyAOHLz-eghNaR3A-HuH0rx93Wfza9aJ35k",
  authDomain: "sigesc-on.firebaseapp.com",
  projectId: "sigesc-on",
  storageBucket: "sigesc-on.firebasestorage.app",
  messagingSenderId: "176313429752",
  appId: "1:176313429752:web:3de9c206c4bd53f7d5d50d"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Exporta o módulo de autenticação
export const auth = getAuth(app);

