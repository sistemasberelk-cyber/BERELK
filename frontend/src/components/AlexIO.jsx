'use client';

import React, { useState, useEffect, useRef } from 'react';
import { apiRequest } from '../services/api';

export default function AlexIO() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([
    { role: 'model', text: '¡Hola! Soy AlexIO, tu asistente de compras inteligente. ¿En qué te puedo ayudar hoy?' }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);

  const messagesEndRef = useRef(null);
  const recognitionRef = useRef(null);

  // Auto-scroll to bottom of chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  // Setup Web Speech API for voice recognition
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (SpeechRecognition) {
        const rec = new SpeechRecognition();
        rec.continuous = false;
        rec.interimResults = false;
        rec.lang = 'es-ES';

        rec.onstart = () => {
          setIsRecording(true);
        };

        rec.onresult = (event) => {
          const transcript = event.results[0][0].transcript;
          setInputValue(transcript);
          setIsRecording(false);
          // Auto send after speech
          handleSendMessage(transcript);
        };

        rec.onerror = (e) => {
          console.error('Speech recognition error', e);
          setIsRecording(false);
        };

        rec.onend = () => {
          setIsRecording(false);
        };

        recognitionRef.current = rec;
      }
    }
  }, [messages]);

  const speak = (text) => {
    if (!voiceEnabled || typeof window === 'undefined') return;
    // Strip emojis and code structures for clean speech synthesis
    const cleanText = text.replace(/[\uE000-\uF8FF]|\uD83C[\uDC00-\uDFFF]|\uD83D[\uDC00-\uDFFF]|[\u2011-\u26FF]|\uD83E[\uDD10-\uDDFF]/g, "");
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = 'es-ES';
    window.speechSynthesis.speak(utterance);
  };

  const startSpeechRecognition = () => {
    if (recognitionRef.current) {
      if (isRecording) {
        recognitionRef.current.stop();
      } else {
        window.speechSynthesis.cancel(); // Stop talking when user starts speaking
        recognitionRef.current.start();
      }
    } else {
      alert('La entrada de voz no es soportada por este navegador. Intente en Google Chrome.');
    }
  };

  const handleSendMessage = async (textToSend = inputValue) => {
    const trimmed = textToSend.trim();
    if (!trimmed || isLoading) return;

    // Clear input if sending from typed state
    if (textToSend === inputValue) {
      setInputValue('');
    }

    const updatedHistory = [...messages];
    setMessages(prev => [...prev, { role: 'user', text: trimmed }]);
    setIsLoading(true);

    try {
      // Map history to Gemini format (user vs model)
      const apiHistory = updatedHistory.map(msg => ({
        role: msg.role === 'user' ? 'user' : 'model',
        parts: [{ text: msg.text }]
      }));

      const res = await apiRequest('/ai/alex-io', {
        method: 'POST',
        body: {
          history: apiHistory,
          new_message: trimmed,
          system_instruction: "Eres AlexIO, un conserje de e-commerce y WMS avanzado. Puedes consultar stock, recomendar productos y dar métricas de ventas. Responde de forma breve, empática y atractiva. Si recomiendas productos, descríbelos de manera tentadora."
        }
      });

      if (res.success && res.response) {
        setMessages(prev => [...prev, { role: 'model', text: res.response }]);
        speak(res.response);
      } else {
        throw new Error('Sin respuesta');
      }
    } catch (e) {
      console.error(e);
      setMessages(prev => [...prev, { role: 'model', text: 'Disculpa, ocurrió un error consultando al cerebro de IA. Por favor intenta de nuevo.' }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed bottom-6 right-6 z-50 font-sans">
      {/* Floating Action Button (FAB) */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="group relative flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-tr from-indigo-600 to-violet-600 text-white shadow-lg shadow-indigo-500/30 transition-all duration-300 hover:scale-110 hover:shadow-indigo-500/50 focus:outline-none focus:ring-2 focus:ring-indigo-400 active:scale-95"
        >
          <span className="absolute -top-1 -right-1 flex h-4.5 w-4.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex h-4.5 w-4.5 rounded-full bg-emerald-500 border-2 border-white dark:border-zinc-950"></span>
          </span>
          <svg className="h-7 w-7 transition-transform group-hover:rotate-12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        </button>
      )}

      {/* Expanded Chat Window */}
      {isOpen && (
        <div className="flex h-[520px] w-[380px] flex-col rounded-2xl border border-zinc-200/50 bg-white/95 shadow-2xl backdrop-blur-md dark:border-zinc-800/50 dark:bg-zinc-950/95 transition-all duration-300 animate-in slide-in-from-bottom-5">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-zinc-200/50 px-4 py-3 dark:border-zinc-800/50 bg-gradient-to-r from-zinc-50 to-zinc-100/50 dark:from-zinc-900/50 dark:to-zinc-900/30 rounded-t-2xl">
            <div className="flex items-center gap-3">
              <div className="relative h-10 w-10 rounded-full bg-gradient-to-tr from-indigo-500 to-violet-500 flex items-center justify-center text-white font-bold text-lg shadow-inner">
                AI
              </div>
              <div>
                <h3 className="font-semibold text-zinc-900 dark:text-zinc-50 text-sm flex items-center gap-1.5">
                  AlexIO
                  <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
                </h3>
                <p className="text-[10px] text-zinc-500 dark:text-zinc-400">Cerebro de Ventas Activo</p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {/* Toggle voice button */}
              <button
                onClick={() => {
                  setVoiceEnabled(!voiceEnabled);
                  if (voiceEnabled) window.speechSynthesis.cancel();
                }}
                className={`p-1.5 rounded-lg transition-colors hover:bg-zinc-205 dark:hover:bg-zinc-800 ${voiceEnabled ? 'text-indigo-600 dark:text-indigo-400' : 'text-zinc-400'}`}
                title={voiceEnabled ? "Desactivar voz de respuesta" : "Activar voz de respuesta"}
              >
                {voiceEnabled ? (
                  <svg className="h-4.5 w-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                  </svg>
                ) : (
                  <svg className="h-4.5 w-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15zm10.707-9.293a1 1 0 010 1.414L14.414 9l1.879 1.879a1 1 0 11-1.414 1.414L13 10.414l-1.879 1.879a1 1 0 11-1.414-1.414L11.586 9 9.707 7.121a1 1 0 111.414-1.414L13 7.586l1.879-1.879a1 1 0 011.414 0z" />
                  </svg>
                )}
              </button>
              <button
                onClick={() => {
                  setIsOpen(false);
                  window.speechSynthesis.cancel();
                }}
                className="p-1.5 text-zinc-400 rounded-lg hover:bg-zinc-200 dark:hover:bg-zinc-800 hover:text-zinc-600 dark:hover:text-zinc-200"
              >
                <svg className="h-4.5 w-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 scrollbar-thin scrollbar-thumb-zinc-200 dark:scrollbar-thumb-zinc-800">
            {messages.map((msg, index) => (
              <div
                key={index}
                className={`flex w-full ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm ${
                    msg.role === 'user'
                      ? 'bg-gradient-to-r from-indigo-600 to-violet-600 text-white rounded-tr-none'
                      : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-100 rounded-tl-none border border-zinc-200/30 dark:border-zinc-800/30'
                  }`}
                >
                  {msg.text}
                </div>
              </div>
            ))}

            {isLoading && (
              <div className="flex w-full justify-start">
                <div className="bg-zinc-100 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-100 max-w-[80%] rounded-2xl rounded-tl-none px-4 py-3 shadow-sm border border-zinc-200/30 dark:border-zinc-800/30 flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-zinc-400 dark:bg-zinc-500 animate-bounce"></span>
                  <span className="h-2 w-2 rounded-full bg-zinc-400 dark:bg-zinc-500 animate-bounce [animation-delay:0.2s]"></span>
                  <span className="h-2 w-2 rounded-full bg-zinc-400 dark:bg-zinc-500 animate-bounce [animation-delay:0.4s]"></span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input Area */}
          <div className="border-t border-zinc-200/50 p-4 dark:border-zinc-800/50 bg-gradient-to-b from-transparent to-zinc-50/50 dark:to-zinc-950/50 rounded-b-2xl">
            <div className="flex items-center gap-2">
              <button
                onClick={startSpeechRecognition}
                className={`p-2.5 rounded-xl border transition-all ${
                  isRecording
                    ? 'border-red-500 bg-red-500 text-white animate-pulse'
                    : 'border-zinc-200 dark:border-zinc-800 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-900'
                }`}
                title={isRecording ? "Escuchando... Haz clic para detener" : "Entrada por Voz"}
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                </svg>
              </button>
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
                placeholder={isRecording ? "Escuchando voz..." : "Pregúntale a AlexIO..."}
                disabled={isRecording}
                className="flex-1 rounded-xl border border-zinc-200 bg-zinc-50 px-3.5 py-2.5 text-sm text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-indigo-500 focus:bg-white dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-50 dark:placeholder-zinc-500 dark:focus:border-indigo-400 dark:focus:bg-zinc-900"
              />
              <button
                onClick={() => handleSendMessage()}
                disabled={!inputValue.trim() || isLoading}
                className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-md shadow-indigo-500/20 transition-all hover:bg-indigo-700 disabled:bg-zinc-200 disabled:text-zinc-400 disabled:shadow-none dark:disabled:bg-zinc-800 dark:disabled:text-zinc-700"
              >
                <svg className="h-5 w-5 rotate-90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
