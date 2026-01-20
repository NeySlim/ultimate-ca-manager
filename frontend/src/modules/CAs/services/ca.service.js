import { api } from '../../../core/api/client';

class CAService {
  async getHierarchy() {
    // TODO: Implement actual API endpoint
    // return api.request('/cas/hierarchy');
    
    // Mock for now
    return new Promise(resolve => {
      setTimeout(() => {
        resolve([
          {
            id: 1,
            name: 'Root CA - UCM Global',
            type: 'Root CA',
            status: 'Active',
            certs: 124,
            expiry: '2035-01-01',
            children: [
              {
                id: 2,
                name: 'Intermediate CA - Web Server',
                type: 'Intermediate',
                status: 'Active',
                certs: 45,
                expiry: '2030-01-01',
                children: []
              },
              {
                id: 3,
                name: 'Intermediate CA - VPN Access',
                type: 'Intermediate',
                status: 'Active',
                certs: 78,
                expiry: '2030-01-01',
                children: []
              }
            ]
          },
          {
            id: 4,
            name: 'Root CA - Legacy 2020',
            type: 'Root CA',
            status: 'Expired',
            certs: 12,
            expiry: '2025-01-01',
            children: []
          }
        ]);
      }, 500);
    });
  }

  async getOrphans() {
     // TODO: Implement actual API endpoint
     // return api.request('/cas/orphans');
     return new Promise(resolve => {
        setTimeout(() => {
            resolve([
                {
                    id: 101,
                    name: 'Imported Intermediate CA',
                    type: 'Intermediate',
                    status: 'Active',
                    certs: 5,
                    expiry: '2028-05-15',
                    issuer: 'External Root CA G2'
                }
            ]);
        }, 500);
     });
  }
  
  async createCA(data) {
    // return api.request('/cas', { method: 'POST', body: JSON.stringify(data) });
    return new Promise(resolve => setTimeout(resolve, 1000));
  }
}

export const caService = new CAService();
