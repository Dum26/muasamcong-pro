import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import { AuthProvider } from './app/AuthProvider';
import { App } from './app/App';
import { ConfirmProvider } from './components/shared/ConfirmProvider';
import './styles.css';
import './legacy-bridge.css';
import './legacy-tokens.css';

createRoot(document.getElementById('root')!).render(
  <React.StrictMode><BrowserRouter><AuthProvider><ConfirmProvider><App /></ConfirmProvider></AuthProvider></BrowserRouter></React.StrictMode>
);
