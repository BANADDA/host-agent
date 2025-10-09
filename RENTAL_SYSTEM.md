# 🏠 Host Agent Rental System

A comprehensive GPU rental system that allows servers to request GPU instances with automatic lifecycle management.

## 🚀 Features

### **Core Functionality**
- ✅ **Rental API Endpoint** (`/rent`) for server requests
- ✅ **PostgreSQL Database** for local rental tracking
- ✅ **Auto-Termination** based on rental duration
- ✅ **Real-time WebSocket Updates** with status progression
- ✅ **GPU Allocation** based on requested type
- ✅ **Dual Authentication** (password + SSH key)
- ✅ **Port Mapping** and environment variable injection

### **Status Progression**
1. **`creating`** - Container creation started
2. **`running`** - Container started with GPU allocated
3. **`ready`** - Instance ready for use with connection info

## 📋 API Reference

### **Rental Request**
```bash
curl -X POST http://your-host-agent:8000/rent \
  -H "Content-Type: application/json" \
  -d '{
    "host_id": "a7d9397f-23a5-454d-a0f0-5373edf7a1f1",
    "gpu_type": "Tesla V100-SXM2-16GB",
    "os_image": "ubuntu:20.04",
    "duration_hours": 2,
    "auth_type": "password",
    "password": "mySecurePassword123",
    "instance_name": "my-gpu-instance",
    "environment_variables": {
      "CUDA_VISIBLE_DEVICES": "0",
      "PYTHONPATH": "/workspace"
    },
    "port_mappings": {
      "8080": "8080",
      "22": "2222"
    }
  }'
```

### **Response Format**
```json
{
  "success": true,
  "message": "Rental 550e8400-e29b-41d4-a716-446655440000 started successfully",
  "container_id": "abc123def456",
  "ssh_port": 2222,
  "web_port": 8080,
  "rental_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

## 🌐 WebSocket Updates

### **Status: Creating**
```json
{
  "instance_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "status": "creating",
  "message": "Starting container creation...",
  "container_id": null
}
```

### **Status: Running**
```json
{
  "instance_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "message": "Container started with container ID: abc123def456",
  "container_id": "abc123def456"
}
```

### **Status: Ready**
```json
{
  "instance_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "status": "ready",
  "message": "GPU instance is ready for use",
  "container_id": "abc123def456",
  "connection_info": {
    "ssh_host": "65.108.33.66",
    "ssh_port": 2222,
    "username": "root",
    "password": "mySecurePassword123"
  },
  "gpu_info": {
    "gpu_id": "0",
    "gpu_name": "Tesla V100-SXM2-16GB",
    "memory_allocated": "16GB"
  },
  "access_info": {
    "ssh_command": "ssh -p 2222 root@65.108.33.66",
    "jupyter_url": "http://65.108.33.66:8080",
    "vnc_url": "vnc://65.108.33.66:5900"
  }
}
```

## 🗄️ Database Schema

### **Rentals Table**
```sql
CREATE TABLE rentals (
    id SERIAL PRIMARY KEY,
    rental_id VARCHAR(255) UNIQUE NOT NULL,
    host_id VARCHAR(255) NOT NULL,
    container_id VARCHAR(255) NOT NULL,
    gpu_type VARCHAR(255) NOT NULL,
    os_image VARCHAR(255) NOT NULL,
    duration_hours INTEGER NOT NULL,
    auth_type VARCHAR(50) NOT NULL,
    password VARCHAR(255),
    ssh_key TEXT,
    instance_name VARCHAR(255) NOT NULL,
    environment_variables JSONB,
    port_mappings JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    status VARCHAR(50) DEFAULT 'active',
    ssh_port INTEGER,
    web_port INTEGER
);
```

## 🚀 Deployment

### **Using Docker Compose (Recommended)**
```bash
# Start the complete system
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f host-agent
```

### **Manual Deployment**
```bash
# Start PostgreSQL
docker run -d --name postgres \
  -e POSTGRES_DB=hostagent \
  -e POSTGRES_USER=hostagent \
  -e POSTGRES_PASSWORD=hostagent123 \
  -p 5432:5432 \
  postgres:15

# Start Host Agent
docker run -d --name host-agent \
  --gpus all \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e API_SERVER_URL="http://66.153.184.209:8000" \
  -e POSTGRES_HOST=postgres \
  -e POSTGRES_PORT=5432 \
  -e POSTGRES_DB=hostagent \
  -e POSTGRES_USER=hostagent \
  -e POSTGRES_PASSWORD=hostagent123 \
  -p 8000:8000 \
  ghcr.io/banadda/host-agent:latest
```

## 🧪 Testing

### **Test Script**
```bash
# Run the test script
python test_rental.py
```

### **Manual Testing**
```bash
# Test rental request
curl -X POST http://localhost:8000/rent \
  -H "Content-Type: application/json" \
  -d '{
    "host_id": "test-host",
    "gpu_type": "Tesla V100-SXM2-16GB",
    "os_image": "ubuntu:20.04",
    "duration_hours": 1,
    "auth_type": "password",
    "password": "test123",
    "instance_name": "test-instance"
  }'

# Test WebSocket connection
wscat -c ws://localhost:8000/ws
```

## 🔧 Configuration

### **Environment Variables**
```bash
# API Server
API_SERVER_URL=http://66.153.184.209:8000

# Database
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=hostagent
POSTGRES_USER=hostagent
POSTGRES_PASSWORD=hostagent123

# Agent
AGENT_PORT=8000
```

### **Docker Compose Configuration**
```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: hostagent
      POSTGRES_USER: hostagent
      POSTGRES_PASSWORD: hostagent123
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hostagent"]
      interval: 10s
      timeout: 5s
      retries: 5

  host-agent:
    build: .
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      - API_SERVER_URL=http://66.153.184.209:8000
      - POSTGRES_HOST=postgres
      - POSTGRES_PORT=5432
      - POSTGRES_DB=hostagent
      - POSTGRES_USER=hostagent
      - POSTGRES_PASSWORD=hostagent123
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    ports:
      - "8000:8000"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]

volumes:
  postgres_data:
```

## 📊 Monitoring

### **Rental Status**
- **Active**: Currently running rentals
- **Expired**: Past due rentals (auto-terminated)
- **Terminated**: Manually or auto-terminated rentals

### **Auto-Termination**
- **Background Timers**: Each rental has a timer
- **Periodic Checks**: Every 5 minutes for expired rentals
- **Database Updates**: Status changes tracked
- **WebSocket Notifications**: Real-time updates

## 🚨 Error Handling

### **Common Errors**
```json
{
  "success": false,
  "message": "No Tesla V100-SXM2-16GB GPUs available on this host"
}
```

### **Error Scenarios**
- ❌ **No Available GPU**: Requested GPU type not available
- ❌ **Image Not Found**: Docker image doesn't exist
- ❌ **Database Error**: PostgreSQL connection issues
- ❌ **Container Start Failed**: Docker runtime errors

## 🔒 Security

### **Authentication Methods**
- **Password**: Root password authentication
- **SSH Key**: Public key authentication

### **Network Security**
- **Random Ports**: SSH and web ports assigned randomly
- **Container Isolation**: Each rental in separate container
- **Auto-Cleanup**: Containers removed after termination

## 📈 Performance

### **Resource Management**
- **GPU Allocation**: One GPU per rental
- **Memory Limits**: Configurable per rental
- **Port Management**: Random port assignment
- **Container Lifecycle**: Automatic cleanup

### **Scalability**
- **Multiple Rentals**: Concurrent rental support
- **Database Pooling**: Connection pooling for PostgreSQL
- **Background Tasks**: Async processing for timers

## 🎯 Use Cases

### **GPU Computing**
- **Machine Learning**: Training and inference
- **Data Science**: Large dataset processing
- **Research**: Scientific computing
- **Development**: GPU application testing

### **Rental Scenarios**
- **Short-term**: 1-2 hour development sessions
- **Medium-term**: 4-8 hour training runs
- **Long-term**: 24+ hour research projects

## 🔄 Lifecycle Management

### **Rental Flow**
1. **Request** → Server sends rental request
2. **Allocation** → GPU and resources allocated
3. **Deployment** → Container created and started
4. **Access** → User connects and works
5. **Monitoring** → Background timer tracks duration
6. **Termination** → Auto-cleanup when expired

### **Auto-Termination**
- **Timer-based**: Each rental has individual timer
- **Database-driven**: Expiration checks every 5 minutes
- **Graceful cleanup**: Containers and resources freed
- **Status updates**: Real-time notifications

---

## 🎉 Ready to Use!

Your host agent now supports the complete rental system with:
- ✅ **Server Integration** - Matches expected response format
- ✅ **Real-time Updates** - WebSocket status progression
- ✅ **Auto-Termination** - Background lifecycle management
- ✅ **Database Tracking** - PostgreSQL rental persistence
- ✅ **Error Handling** - Comprehensive error responses

The system is ready for production use! 🚀
