/**
 * API Service Layer
 * Centralized API calls with error handling
 */

const API_BASE = '/api';

interface FetchOptions extends RequestInit {
  params?: Record<string, string | number>;
}

class ApiClient {
  private async request<T>(
    endpoint: string,
    options: FetchOptions = {}
  ): Promise<T> {
    const { params, ...fetchOptions } = options;

    // Build URL with query params
    let url = `${API_BASE}${endpoint}`;
    if (params) {
      const queryString = new URLSearchParams(
        Object.entries(params).map(([k, v]) => [k, String(v)])
      ).toString();
      url += `?${queryString}`;
    }

    const response = await fetch(url, {
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...fetchOptions.headers,
      },
      ...fetchOptions,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Request failed' }));
      throw new Error(error.error || error.message || 'Request failed');
    }

    return response.json();
  }

  // Certificates
  async getCertificates(params?: { page?: number; per_page?: number; status?: string }) {
    return this.request('/certificates', { params });
  }

  async getCertificate(id: number) {
    return this.request(`/certificates/${id}`);
  }

  async createCertificate(data: any) {
    return this.request('/certificates', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async deleteCertificate(id: number) {
    return this.request(`/certificates/${id}`, { method: 'DELETE' });
  }

  async revokeCertificate(id: number, reason?: string) {
    return this.request(`/certificates/${id}/revoke`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  }

  // CAs
  async getCAs(params?: { page?: number; per_page?: number }) {
    return this.request('/cas', { params });
  }

  async getCA(id: number) {
    return this.request(`/cas/${id}`);
  }

  async createCA(data: any) {
    return this.request('/cas', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async deleteCA(id: number) {
    return this.request(`/cas/${id}`, { method: 'DELETE' });
  }

  // Users
  async getUsers(params?: { page?: number; per_page?: number }) {
    return this.request('/settings/users', { params });
  }

  async createUser(data: any) {
    return this.request('/settings/users', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateUser(id: number, data: any) {
    return this.request(`/settings/users/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async deleteUser(id: number) {
    return this.request(`/settings/users/${id}`, { method: 'DELETE' });
  }

  // Settings
  async getGeneralSettings() {
    return this.request('/settings/general');
  }

  async updateGeneralSettings(data: any) {
    return this.request('/settings/general', {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async getEmailSettings() {
    return this.request('/settings/email');
  }

  async updateEmailSettings(data: any) {
    return this.request('/settings/email', {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  // Backup
  async createBackup() {
    return this.request('/settings/backup/create', { method: 'POST' });
  }

  async getBackupHistory(params?: { page?: number; per_page?: number }) {
    return this.request('/settings/backup/history', { params });
  }

  async downloadBackup(id: number) {
    const url = `${API_BASE}/settings/backup/${id}/download`;
    window.open(url, '_blank');
  }

  async deleteBackup(id: number) {
    return this.request(`/settings/backup/${id}`, { method: 'DELETE' });
  }

  // Dashboard
  async getDashboardStats() {
    return this.request('/dashboard/stats');
  }

  async getRecentActivity(params?: { limit?: number }) {
    return this.request('/dashboard/activity', { params });
  }

  // Account
  async getProfile() {
    return this.request('/account/profile');
  }

  async updateProfile(data: any) {
    return this.request('/account/profile', {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async changePassword(data: { current_password: string; new_password: string; confirm_password: string }) {
    return this.request('/account/password', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getApiKeys() {
    return this.request('/account/apikeys');
  }

  async createApiKey(data: { name: string; permissions: string[]; expires_days?: number }) {
    return this.request('/account/apikeys', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async deleteApiKey(id: number) {
    return this.request(`/account/apikeys/${id}`, { method: 'DELETE' });
  }

  async getSessions() {
    return this.request('/account/sessions');
  }

  async revokeSession(id: number) {
    return this.request(`/account/sessions/${id}`, { method: 'DELETE' });
  }
}

export const api = new ApiClient();
