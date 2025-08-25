import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

const Login = () => {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleLogin = (e) => {
    e.preventDefault();
    // Bu basit bir şifre kontrolüdür. 
    // Gerçek bir uygulamada daha güvenli bir kimlik doğrulama yöntemi kullanılmalıdır.
    if (password === 'admin123') {
      localStorage.setItem('authToken', 'authenticated');
      navigate('/');
    } else {
      setError('Geçersiz şifre');
    }
  };

  return (
    <div className="login-container">
      <form onSubmit={handleLogin} className="login-form">
        <h2 className="text-2xl text-center mb-6">Shopify XML Sync</h2>
        <p className="text-center mb-6" style={{color: '#6b7280'}}>Panele erişim için şifrenizi girin</p>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Şifre"
          className="input"
          required
        />
        <button type="submit" className="btn" style={{width: '100%'}}>
          Giriş Yap
        </button>
        {error && <div className="error">{error}</div>}
        <div style={{marginTop: '20px', padding: '12px', background: '#f3f4f6', borderRadius: '8px', fontSize: '12px', color: '#6b7280'}}>
          Demo şifre: admin123
        </div>
      </form>
    </div>
  );
};

export default Login;
