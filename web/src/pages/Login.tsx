import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSocket } from '../contexts/SocketContext';

export default function Login() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const navigate = useNavigate();
    const { connect } = useSocket();

    const handleAuth = async (isLogin: boolean) => {
        try {
            const endpoint = isLogin ? '/api/v1/auth/login' : '/api/v1/auth/register';
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });

            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Authentication failed');

            if (!isLogin) {
                alert("Registration successful! Please login.");
                return;
            }

            // Store token and redirect
            localStorage.setItem('fh_token', data.token);
            connect(data.token);
            navigate('/lobby');
        } catch (err: any) {
            setError(err.message);
        }
    };

    return (
        <div className="flex flex-col items-center justify-center min-h-[80vh]">
            <div className="bg-gray-800 p-8 rounded-xl shadow-2xl w-full max-w-sm border border-gray-700">
                <h1 className="text-3xl font-bold mb-6 text-green-400 text-center">Fenghua</h1>

                {error && <div className="bg-red-900/50 border border-red-500 text-red-200 px-4 py-2 rounded mb-4 text-sm">{error}</div>}

                <input
                    className="w-full bg-gray-900 text-white border border-gray-600 rounded px-4 py-2 mb-4 focus:outline-none focus:border-green-500 transition-colors"
                    placeholder="Username"
                    value={username}
                    onChange={e => setUsername(e.target.value)}
                />
                <input
                    type="password"
                    className="w-full bg-gray-900 text-white border border-gray-600 rounded px-4 py-2 mb-6 focus:outline-none focus:border-green-500 transition-colors"
                    placeholder="Password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                />

                <div className="flex gap-4">
                    <button
                        className="flex-1 bg-green-600 hover:bg-green-500 text-white font-semibold py-2 rounded transition-colors"
                        onClick={() => handleAuth(true)}>Login</button>
                    <button
                        className="flex-1 bg-gray-700 hover:bg-gray-600 text-white font-semibold py-2 rounded transition-colors"
                        onClick={() => handleAuth(false)}>Register</button>
                </div>
            </div>
        </div>
    );
}
