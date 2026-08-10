'use client';
import React, { useState } from 'react';
import { apiRequest } from '@/services/api';

export default function WebBuilder() {
  const [activeTab, setActiveTab] = useState('landing');
  
  // Landing State
  const [niche, setNiche] = useState('');
  const [audience, setAudience] = useState('');
  const [tone, setTone] = useState('Antigravity (Futurista, Épico)');
  const [landingResult, setLandingResult] = useState(null);
  const [loadingLanding, setLoadingLanding] = useState(false);

  // Product State
  const [productName, setProductName] = useState('');
  const [features, setFeatures] = useState('');
  const [productResult, setProductResult] = useState('');
  const [loadingProduct, setLoadingProduct] = useState(false);

  // Chatbot State
  const [chatInstruction, setChatInstruction] = useState('Eres un asistente virtual de ventas amable y futurista.');
  const [chatHistory, setChatHistory] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [loadingChat, setLoadingChat] = useState(false);

  const generateLanding = async () => {
    setLoadingLanding(true);
    try {
      const res = await apiRequest('/ai/landing-copy', {
        method: 'POST',
        body: JSON.stringify({ niche, audience, tone })
      });
      if (res.success) setLandingResult(res.copy);
    } catch (e) {
      alert("Error: " + e.message);
    }
    setLoadingLanding(false);
  };

  const generateProduct = async () => {
    setLoadingProduct(true);
    try {
      const res = await apiRequest('/ai/product-description', {
        method: 'POST',
        body: JSON.stringify({ product_name: productName, features })
      });
      if (res.success) setProductResult(res.description);
    } catch (e) {
      alert("Error: " + e.message);
    }
    setLoadingProduct(false);
  };

  const sendChatMessage = async () => {
    if (!chatInput.trim()) return;
    const newMsg = { role: 'user', parts: [{ text: chatInput }] };
    const newHistory = [...chatHistory, newMsg];
    setChatHistory(newHistory);
    setChatInput('');
    setLoadingChat(true);
    try {
      const res = await apiRequest('/ai/chat', {
        method: 'POST',
        body: JSON.stringify({
          history: chatHistory,
          new_message: chatInput,
          system_instruction: chatInstruction
        })
      });
      if (res.success) {
        setChatHistory([...newHistory, { role: 'model', parts: [{ text: res.response }] }]);
      }
    } catch (e) {
      alert("Error: " + e.message);
    }
    setLoadingChat(false);
  };

  return (
    <div className="min-h-screen bg-[#050505] text-white p-8 font-sans selection:bg-purple-500/30">
      
      {/* HEADER */}
      <div className="max-w-5xl mx-auto mb-12 relative">
        <div className="absolute -top-10 -left-10 w-40 h-40 bg-purple-600/20 rounded-full blur-3xl pointer-events-none"></div>
        <div className="absolute top-10 right-10 w-60 h-60 bg-blue-600/10 rounded-full blur-3xl pointer-events-none"></div>
        
        <h1 className="text-4xl md:text-5xl font-black mb-4 tracking-tighter bg-gradient-to-r from-purple-400 via-blue-400 to-cyan-300 bg-clip-text text-transparent">
          VibeCloud Web Creator ✨
        </h1>
        <p className="text-gray-400 text-lg max-w-2xl">
          Construye tu presencia digital impulsada por Inteligencia Artificial. Diseña landing pages, descripciones de productos y entrena a tu asistente virtual en segundos.
        </p>
      </div>

      {/* TABS */}
      <div className="max-w-5xl mx-auto mb-8 flex space-x-4 border-b border-white/10 pb-2">
        {['landing', 'product', 'chatbot'].map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-6 py-3 rounded-t-lg font-bold transition-all duration-300 ${
              activeTab === tab 
                ? 'bg-white/10 text-white border-b-2 border-purple-500' 
                : 'text-gray-500 hover:text-gray-300 hover:bg-white/5'
            }`}
          >
            {tab === 'landing' ? 'Landing Page' : tab === 'product' ? 'Productos' : 'Chatbot'}
          </button>
        ))}
      </div>

      {/* CONTENT */}
      <div className="max-w-5xl mx-auto">
        
        {/* LANDING TAB */}
        {activeTab === 'landing' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6">
              <h2 className="text-xl font-bold mb-6 text-purple-300">Configuración de Landing</h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-bold text-gray-400 uppercase mb-2">Nicho de Negocio</label>
                  <input type="text" className="w-full bg-black/50 border border-white/10 rounded-lg p-3 text-white focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition-all" placeholder="Ej: Venta de zapatillas de running" value={niche} onChange={e => setNiche(e.target.value)} />
                </div>
                <div>
                  <label className="block text-xs font-bold text-gray-400 uppercase mb-2">Público Objetivo</label>
                  <input type="text" className="w-full bg-black/50 border border-white/10 rounded-lg p-3 text-white focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition-all" placeholder="Ej: Deportistas amateurs de 20 a 40 años" value={audience} onChange={e => setAudience(e.target.value)} />
                </div>
                <div>
                  <label className="block text-xs font-bold text-gray-400 uppercase mb-2">Tono de la Marca</label>
                  <select className="w-full bg-black/50 border border-white/10 rounded-lg p-3 text-white outline-none" value={tone} onChange={e => setTone(e.target.value)}>
                    <option>Antigravity (Futurista, Épico)</option>
                    <option>Corporativo y Profesional</option>
                    <option>Divertido y Cercano</option>
                    <option>Agresivo y Vendedor</option>
                  </select>
                </div>
                <button onClick={generateLanding} disabled={loadingLanding} className="w-full mt-4 bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 text-white font-bold py-3 px-4 rounded-lg shadow-[0_0_15px_rgba(168,85,247,0.4)] transition-all flex justify-center items-center">
                  {loadingLanding ? <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div> : "Generar Copy Cósmico ✨"}
                </button>
              </div>
            </div>
            
            <div className="bg-gradient-to-br from-purple-900/20 to-blue-900/20 backdrop-blur-xl border border-white/10 rounded-2xl p-6 min-h-[400px]">
              <h2 className="text-xl font-bold mb-6 text-blue-300">Vista Previa</h2>
              {landingResult ? (
                <div className="space-y-6">
                  <h1 className="text-4xl font-black leading-tight">{landingResult.h1}</h1>
                  <h2 className="text-2xl text-purple-300 font-semibold">{landingResult.h2}</h2>
                  <ul className="space-y-3">
                    {landingResult.bullets.map((b, i) => (
                      <li key={i} className="flex items-start">
                        <span className="text-blue-400 mr-2">🚀</span>
                        <span className="text-gray-300">{b}</span>
                      </li>
                    ))}
                  </ul>
                  <button className="bg-white text-black font-black py-4 px-8 rounded-full shadow-[0_0_20px_rgba(255,255,255,0.3)] hover:scale-105 transition-transform">
                    {landingResult.cta}
                  </button>
                </div>
              ) : (
                <div className="h-full flex items-center justify-center text-gray-500 italic">
                  Llena los datos y presiona generar para ver la magia.
                </div>
              )}
            </div>
          </div>
        )}

        {/* PRODUCT TAB */}
        {activeTab === 'product' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6">
              <h2 className="text-xl font-bold mb-6 text-purple-300">Descripción de Producto</h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-bold text-gray-400 uppercase mb-2">Nombre del Producto</label>
                  <input type="text" className="w-full bg-black/50 border border-white/10 rounded-lg p-3 text-white outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition-all" placeholder="Ej: Zapatillas Antigravity X1" value={productName} onChange={e => setProductName(e.target.value)} />
                </div>
                <div>
                  <label className="block text-xs font-bold text-gray-400 uppercase mb-2">Características Clave</label>
                  <textarea className="w-full bg-black/50 border border-white/10 rounded-lg p-3 text-white h-32 outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition-all" placeholder="Ej: Suela de grafeno, ultra livianas, diseño aerodinámico, colores neón..." value={features} onChange={e => setFeatures(e.target.value)}></textarea>
                </div>
                <button onClick={generateProduct} disabled={loadingProduct} className="w-full mt-4 bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white font-bold py-3 px-4 rounded-lg shadow-[0_0_15px_rgba(6,182,212,0.4)] transition-all flex justify-center items-center">
                  {loadingProduct ? <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div> : "Crear Descripción SEO ✨"}
                </button>
              </div>
            </div>

            <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6 min-h-[400px] overflow-y-auto">
              <h2 className="text-xl font-bold mb-6 text-cyan-300">Resultado HTML</h2>
              {productResult ? (
                <div className="prose prose-invert max-w-none" dangerouslySetInnerHTML={{__html: productResult}}></div>
              ) : (
                <div className="h-full flex items-center justify-center text-gray-500 italic">
                  Aquí aparecerá tu descripción lista para la web.
                </div>
              )}
            </div>
          </div>
        )}

        {/* CHATBOT TAB */}
        {activeTab === 'chatbot' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div className="lg:col-span-1 bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6">
              <h2 className="text-xl font-bold mb-6 text-purple-300">Cerebro del Bot</h2>
              <div>
                <label className="block text-xs font-bold text-gray-400 uppercase mb-2">Instrucción del Sistema (Reglas)</label>
                <textarea 
                  className="w-full bg-black/50 border border-white/10 rounded-lg p-3 text-white h-64 outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition-all text-sm font-mono" 
                  value={chatInstruction} 
                  onChange={e => setChatInstruction(e.target.value)}
                ></textarea>
              </div>
              <button 
                onClick={() => setChatHistory([])}
                className="w-full mt-4 bg-white/10 hover:bg-white/20 text-white font-bold py-2 px-4 rounded-lg transition-all"
              >
                Reiniciar Memoria
              </button>
            </div>

            <div className="lg:col-span-2 bg-black/40 backdrop-blur-xl border border-white/10 rounded-2xl flex flex-col overflow-hidden h-[600px]">
              <div className="bg-white/5 p-4 border-b border-white/10 flex items-center">
                <div className="w-3 h-3 bg-green-500 rounded-full mr-3 animate-pulse"></div>
                <h3 className="font-bold">Chat de Prueba</h3>
              </div>
              
              <div className="flex-1 overflow-y-auto p-6 space-y-4">
                {chatHistory.length === 0 && (
                  <div className="text-center text-gray-500 my-10">Envía un mensaje para iniciar la conversación con tu nuevo bot.</div>
                )}
                {chatHistory.map((msg, i) => (
                  <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[80%] rounded-2xl px-5 py-3 ${
                      msg.role === 'user' 
                        ? 'bg-purple-600 text-white rounded-br-none' 
                        : 'bg-white/10 text-gray-200 rounded-bl-none'
                    }`}>
                      {msg.parts[0].text}
                    </div>
                  </div>
                ))}
                {loadingChat && (
                  <div className="flex justify-start">
                    <div className="bg-white/10 rounded-2xl rounded-bl-none px-5 py-4 flex space-x-2">
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{animationDelay: '0.2s'}}></div>
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{animationDelay: '0.4s'}}></div>
                    </div>
                  </div>
                )}
              </div>

              <div className="p-4 bg-white/5 border-t border-white/10">
                <form 
                  onSubmit={(e) => { e.preventDefault(); sendChatMessage(); }}
                  className="flex space-x-2"
                >
                  <input 
                    type="text" 
                    className="flex-1 bg-black/50 border border-white/10 rounded-full px-5 py-3 text-white outline-none focus:border-purple-500 transition-all" 
                    placeholder="Escribe un mensaje de prueba..." 
                    value={chatInput}
                    onChange={e => setChatInput(e.target.value)}
                  />
                  <button 
                    type="submit"
                    disabled={loadingChat || !chatInput.trim()}
                    className="bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-bold p-3 w-12 h-12 rounded-full flex items-center justify-center transition-all"
                  >
                    🚀
                  </button>
                </form>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
