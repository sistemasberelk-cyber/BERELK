const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

let isRefreshing = false;
let refreshSubscribers = [];

function subscribeTokenRefresh(cb) {
  refreshSubscribers.push(cb);
}

function onRefreshed(token) {
  refreshSubscribers.forEach(cb => cb(token));
  refreshSubscribers = [];
}

export async function apiRequest(path, options = {}) {
  let token = null;
  if (typeof window !== 'undefined') {
    token = localStorage.getItem('accessToken');
  }

  if (!options.headers) {
    options.headers = {};
  }

  if (typeof window !== 'undefined') {
    const hostname = window.location.host;
    const baseDomain = process.env.NEXT_PUBLIC_BASE_DOMAIN || 'vibecloud-frontend.onrender.com';
    let subdomain = '';
    if (hostname && hostname.includes('.') && !hostname.startsWith('localhost') && !hostname.startsWith('127.0.0.1')) {
      if (hostname.endsWith(baseDomain)) {
        subdomain = hostname.replace('.' + baseDomain, '');
      } else {
        subdomain = hostname.split('.')[0];
      }
    }
    if (subdomain) {
      options.headers['x-tenant-subdomain'] = subdomain.toLowerCase();
    }
  }

  if (token) {
    options.headers['Authorization'] = `Bearer ${token}`;
  }

  if (options.body && typeof options.body === 'object') {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, options);

  if (response.status === 401 && typeof window !== 'undefined') {
    const refreshToken = localStorage.getItem('refreshToken');
    if (refreshToken) {
      if (!isRefreshing) {
        isRefreshing = true;
        try {
          const refreshResponse = await fetch(`${API_BASE_URL}/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken })
          });

          if (refreshResponse.ok) {
            const data = await refreshResponse.json();
            localStorage.setItem('accessToken', data.access_token);
            localStorage.setItem('refreshToken', data.refresh_token);
            isRefreshing = false;
            onRefreshed(data.access_token);
          } else {
            isRefreshing = false;
            localStorage.removeItem('accessToken');
            localStorage.removeItem('refreshToken');
            window.location.href = '/login';
            throw new Error('Sesión expirada');
          }
        } catch (err) {
          isRefreshing = false;
          localStorage.removeItem('accessToken');
          localStorage.removeItem('refreshToken');
          window.location.href = '/login';
          throw err;
        }
      }

      // Return a promise that resolves when the token refresh finishes
      return new Promise((resolve) => {
        subscribeTokenRefresh((newToken) => {
          options.headers['Authorization'] = `Bearer ${newToken}`;
          // Parse again options.body if it was stringified
          resolve(
            fetch(`${API_BASE_URL}${path}`, options).then((r) => {
              if (!r.ok) throw new Error('API Request failed after refresh');
              return r.json();
            })
          );
        });
      });
    } else {
      window.location.href = '/login';
      throw new Error('No autenticado');
    }
  }

  if (!response.ok) {
    const errData = await response.json().catch(() => ({}));
    throw new Error(errData.detail || 'Error en la petición de API');
  }

  // Handle empty responses or standard JSON
  if (response.status === 204) {
    return null;
  }
  return response.json();
}
