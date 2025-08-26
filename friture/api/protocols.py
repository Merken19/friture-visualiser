#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2025 Friture Contributors

# This file is part of Friture.
#
# Friture is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as published by
# the Free Software Foundation.
#
# Friture is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Friture.  If not, see <http://www.gnu.org/licenses/>.

"""
Network Protocols for Friture Streaming API

This module implements various network protocols for streaming audio analysis
data to external applications. Each protocol is optimized for different
use cases and network conditions.

Protocol Characteristics:
- WebSocket: Full-duplex, low latency, good for web applications
- TCP: Reliable delivery, connection-oriented, good for critical data
- UDP: Low latency, connectionless, good for real-time applications
- HTTP SSE: Server-sent events, good for web dashboards

Design Principles:
- Non-blocking I/O to avoid impacting Friture performance
- Automatic connection management and recovery
- Configurable serialization and compression
- Comprehensive error handling
- Performance monitoring
"""

import json
import logging
import socket
import threading
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Callable
import asyncio

from PyQt5.QtCore import QObject, pyqtSignal, QThread


class StreamingProtocol(QObject):
    """
    Abstract base class for streaming protocols.
    
    All protocols must implement the abstract methods and follow the
    established patterns for connection management and data transmission.
    
    Signals:
        client_connected: Emitted when a client connects
        client_disconnected: Emitted when a client disconnects
        data_sent: Emitted when data is successfully sent
        error_occurred: Emitted when an error occurs
    """
    
    client_connected = pyqtSignal(str)  # client_id
    client_disconnected = pyqtSignal(str)  # client_id
    data_sent = pyqtSignal(str, int)  # client_id, bytes_sent
    error_occurred = pyqtSignal(str)  # error_message
    
    def __init__(self, host: str = 'localhost', port: int = 8080, parent=None):
        super().__init__(parent)
        
        self.host = host
        self.port = port
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._is_running = False
        self._clients: Dict[str, Any] = {}
        self._statistics = {
            'total_connections': 0,
            'active_connections': 0,
            'total_bytes_sent': 0,
            'total_messages_sent': 0
        }
    
    @abstractmethod
    def start(self) -> None:
        """Start the protocol server."""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Stop the protocol server."""
        pass
    
    @abstractmethod
    def send_data(self, data: str, client_id: Optional[str] = None) -> None:
        """
        Send data to clients.
        
        Args:
            data: Serialized data to send
            client_id: Specific client to send to (None = broadcast)
        """
        pass
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get protocol statistics.
        
        Returns:
            Dictionary of performance statistics
        """
        stats = self._statistics.copy()
        stats['is_running'] = self._is_running
        stats['host'] = self.host
        stats['port'] = self.port
        return stats


class WebSocketProtocol(StreamingProtocol):
    """
    WebSocket protocol implementation.

    Provides full-duplex communication suitable for web applications
    and real-time dashboards. Supports multiple concurrent clients
    with automatic connection management.
    """
    def __init__(self, host: str = 'localhost', port: int = 8765, parent=None):
        super().__init__(host, port, parent)

        self._server = None
        self._server_thread = None
        self._loop = None

    def start(self) -> None:
        """Start the WebSocket server."""
        if self._is_running:
            return

        self._is_running = True
        self._server_thread = threading.Thread(target=self._run_server, daemon=True)
        self._server_thread.start()
        self.logger.info(f"WebSocket server starting on {self.host}:{self.port}")

    def stop(self) -> None:
        """Stop the WebSocket server."""
        if not self._is_running:
            return

        self._is_running = False

        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._server_thread:
            self._server_thread.join(timeout=5.0)

        self.logger.info("WebSocket server stopped")

    def _run_server(self) -> None:
        """Run the WebSocket server (in separate thread)."""
        try:
            import websockets

            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            async def server_main():
                async with websockets.serve(self._handle_client, self.host, self.port):
                    self.logger.info(f"WebSocket server started on {self.host}:{self.port}")
                    await asyncio.Future()  # run forever

            self._loop.run_until_complete(server_main())

        except ImportError:
            self.logger.error("websockets library not available. Install with: pip install websockets")
            self.error_occurred.emit("websockets library not available")
        except Exception as e:
            self.logger.error(f"WebSocket server error: {e}")
            self.error_occurred.emit(str(e))

    async def _handle_client(self, websocket) -> None:
        """Handle a WebSocket client connection."""
        client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        
        # Try to get path from request, fallback to "/" if not available
        try:
            path = websocket.request.path if hasattr(websocket, 'request') else "/"
        except AttributeError:
            path = "/"
        
        self._clients[client_id] = websocket
        self._statistics['total_connections'] += 1
        self._statistics['active_connections'] += 1

        self.client_connected.emit(client_id)
        self.logger.info(f"WebSocket client connected: {client_id} (path={path})")

        try:
            await websocket.wait_closed()
        except Exception as e:
            self.logger.error(f"WebSocket client error: {e}")
        finally:
            if client_id in self._clients:
                del self._clients[client_id]
            self._statistics['active_connections'] -= 1
            self.client_disconnected.emit(client_id)
            self.logger.info(f"WebSocket client disconnected: {client_id}")
                                    
    def send_data(self, data: str, client_id: Optional[str] = None) -> None:
        """Send data to WebSocket clients."""
        if not self._is_running or not self._clients:
            return

        try:
            if client_id and client_id in self._clients:
                clients = [self._clients[client_id]]
            else:
                clients = list(self._clients.values())

            for websocket in clients:
                if self._loop:
                    asyncio.run_coroutine_threadsafe(
                        self._send_to_client(websocket, data), self._loop
                    )

        except Exception as e:
            self.logger.error(f"Error sending WebSocket data: {e}")
            self.error_occurred.emit(str(e))

    async def _send_to_client(self, websocket, data: str) -> None:
        """Send data to a specific WebSocket client."""
        try:
            await websocket.send(data)
            self._statistics['total_bytes_sent'] += len(data.encode('utf-8'))
            self._statistics['total_messages_sent'] += 1
        except Exception as e:
            self.logger.error(f"Error sending to WebSocket client: {e}")

class TCPProtocol(StreamingProtocol):
    """
    TCP protocol implementation.

    Provides reliable, connection-oriented communication suitable for
    applications requiring guaranteed delivery of audio analysis data.
    """
    def __init__(self, host: str = 'localhost', port: int = 8766, parent=None):
        super().__init__(host, port, parent)

        self._server_socket = None
        self._server_thread = None
        self._client_threads: List[threading.Thread] = []

    def start(self) -> None:
        """Start the TCP server."""
        if self._is_running:
            return

        self._is_running = True

        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind((self.host, self.port))
            self._server_socket.listen(5)

            self._server_thread = threading.Thread(target=self._accept_clients, daemon=True)
            self._server_thread.start()

            self.logger.info(f"TCP server started on {self.host}:{self.port}")

        except Exception as e:
            self.logger.error(f"Failed to start TCP server: {e}")
            self.error_occurred.emit(str(e))
            self._is_running = False

    def stop(self) -> None:
        """Stop the TCP server."""
        if not self._is_running:
            return

        self._is_running = False

        if self._server_socket:
            self._server_socket.close()

        if self._server_thread:
            self._server_thread.join(timeout=5.0)

        for thread in self._client_threads:
            thread.join(timeout=1.0)

        self.logger.info("TCP server stopped")

    def _accept_clients(self) -> None:
        """Accept incoming client connections."""
        while self._is_running:
            try:
                client_socket, address = self._server_socket.accept()
                client_id = f"{address[0]}:{address[1]}"

                self._clients[client_id] = client_socket
                self._statistics['total_connections'] += 1
                self._statistics['active_connections'] += 1

                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, client_id),
                    daemon=True
                )
                client_thread.start()
                self._client_threads.append(client_thread)

                self.client_connected.emit(client_id)
                self.logger.info(f"TCP client connected: {client_id}")

            except Exception as e:
                if self._is_running:
                    self.logger.error(f"Error accepting TCP client: {e}")

    def _handle_client(self, client_socket, client_id: str) -> None:
        """Handle a TCP client connection."""
        try:
            while self._is_running:
                # Keep-alive loop; extend to handle inbound data if needed
                time.sleep(1.0)
        except Exception as e:
            self.logger.error(f"TCP client handler error: {e}")
        finally:
            client_socket.close()
            if client_id in self._clients:
                del self._clients[client_id]
            self._statistics['active_connections'] -= 1
            self.client_disconnected.emit(client_id)
            self.logger.info(f"TCP client disconnected: {client_id}")

    def send_data(self, data: str, client_id: Optional[str] = None) -> None:
        """Send data to TCP clients."""
        if not self._is_running or not self._clients:
            return

        message = f"{len(data)}\n{data}"
        message_bytes = message.encode('utf-8')

        try:
            if client_id and client_id in self._clients:
                clients = [(client_id, self._clients[client_id])]
            else:
                clients = list(self._clients.items())

            for cid, client_socket in clients:
                try:
                    client_socket.sendall(message_bytes)
                    self._statistics['total_bytes_sent'] += len(message_bytes)
                    self._statistics['total_messages_sent'] += 1
                    self.data_sent.emit(cid, len(message_bytes))
                except Exception as e:
                    self.logger.error(f"Error sending to TCP client {cid}: {e}")

        except Exception as e:
            self.logger.error(f"Error sending TCP data: {e}")
            self.error_occurred.emit(str(e))

class UDPProtocol(StreamingProtocol):
    """
    UDP protocol implementation.
    
    Provides low-latency, connectionless communication suitable for
    real-time applications where occasional data loss is acceptable.
    """
    
    def __init__(self, host: str = 'localhost', port: int = 8767, parent=None):
        super().__init__(host, port, parent)
        
        self._socket = None
        self._client_addresses = set()
    
    def start(self) -> None:
        """Start the UDP server."""
        if self._is_running:
            return
        
        self._is_running = True
        
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.bind((self.host, self.port))
            
            self.logger.info(f"UDP server started on {self.host}:{self.port}")
            
        except Exception as e:
            self.logger.error(f"Failed to start UDP server: {e}")
            self.error_occurred.emit(str(e))
            self._is_running = False
    
    def stop(self) -> None:
        """Stop the UDP server."""
        if not self._is_running:
            return
        
        self._is_running = False
        
        if self._socket:
            self._socket.close()
        
        self.logger.info("UDP server stopped")
    
    def add_client(self, client_host: str, client_port: int) -> None:
        """
        Add a UDP client address for broadcasting.
        
        Args:
            client_host: Client hostname/IP
            client_port: Client port
        """
        address = (client_host, client_port)
        self._client_addresses.add(address)
        client_id = f"{client_host}:{client_port}"
        self.client_connected.emit(client_id)
        self.logger.info(f"Added UDP client: {client_id}")
    
    def remove_client(self, client_host: str, client_port: int) -> None:
        """
        Remove a UDP client address.
        
        Args:
            client_host: Client hostname/IP
            client_port: Client port
        """
        address = (client_host, client_port)
        self._client_addresses.discard(address)
        client_id = f"{client_host}:{client_port}"
        self.client_disconnected.emit(client_id)
        self.logger.info(f"Removed UDP client: {client_id}")
    
    def send_data(self, data: str, client_id: Optional[str] = None) -> None:
        """
        Send data to UDP clients.
        
        Args:
            data: Serialized data to send
            client_id: Specific client to send to (None = broadcast)
        """
        if not self._is_running or not self._socket or not self._client_addresses:
            return
        
        message_bytes = data.encode('utf-8')
        
        # UDP has size limitations, check message size
        if len(message_bytes) > 65507:  # Max UDP payload
            self.logger.warning(f"UDP message too large: {len(message_bytes)} bytes")
            return
        
        try:
            if client_id:
                # Send to specific client
                host, port = client_id.split(':')
                address = (host, int(port))
                if address in self._client_addresses:
                    self._socket.sendto(message_bytes, address)
                    self._statistics['total_bytes_sent'] += len(message_bytes)
                    self._statistics['total_messages_sent'] += 1
                    self.data_sent.emit(client_id, len(message_bytes))
            else:
                # Broadcast to all clients
                for address in self._client_addresses:
                    try:
                        self._socket.sendto(message_bytes, address)
                        self._statistics['total_bytes_sent'] += len(message_bytes)
                        self._statistics['total_messages_sent'] += 1
                        cid = f"{address[0]}:{address[1]}"
                        self.data_sent.emit(cid, len(message_bytes))
                    except Exception as e:
                        self.logger.error(f"Error sending to UDP client {address}: {e}")
            
        except Exception as e:
            self.logger.error(f"Error sending UDP data: {e}")
            self.error_occurred.emit(str(e))


class HTTPSSEProtocol(StreamingProtocol):
    """
    HTTP Server-Sent Events protocol implementation.
    
    Provides one-way streaming suitable for web dashboards and monitoring
    applications. Clients connect via standard HTTP and receive real-time
    updates through the SSE protocol.
    """
    
    def __init__(self, host: str = 'localhost', port: int = 8768, parent=None):
        super().__init__(host, port, parent)
        
        self._server_socket = None
        self._server_thread = None
        self._client_threads: List[threading.Thread] = []
    
    def start(self) -> None:
        """Start the HTTP SSE server."""
        if self._is_running:
            return
        
        self._is_running = True
        
        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind((self.host, self.port))
            self._server_socket.listen(5)
            
            self._server_thread = threading.Thread(target=self._accept_clients, daemon=True)
            self._server_thread.start()
            
            self.logger.info(f"HTTP SSE server started on {self.host}:{self.port}")
            
        except Exception as e:
            self.logger.error(f"Failed to start HTTP SSE server: {e}")
            self.error_occurred.emit(str(e))
            self._is_running = False
    
    def stop(self) -> None:
        """Stop the HTTP SSE server."""
        if not self._is_running:
            return
        
        self._is_running = False
        
        if self._server_socket:
            self._server_socket.close()
        
        if self._server_thread:
            self._server_thread.join(timeout=5.0)
        
        for thread in self._client_threads:
            thread.join(timeout=1.0)
        
        self.logger.info("HTTP SSE server stopped")
    
    def _accept_clients(self) -> None:
        """Accept incoming HTTP connections."""
        while self._is_running:
            try:
                client_socket, address = self._server_socket.accept()
                client_id = f"{address[0]}:{address[1]}"
                
                # Start client handler thread
                client_thread = threading.Thread(
                    target=self._handle_http_client,
                    args=(client_socket, client_id),
                    daemon=True
                )
                client_thread.start()
                self._client_threads.append(client_thread)
                
            except Exception as e:
                if self._is_running:
                    self.logger.error(f"Error accepting HTTP client: {e}")
    
    def _handle_http_client(self, client_socket, client_id: str) -> None:
        """Handle an HTTP SSE client connection."""
        try:
            # Read HTTP request
            request = client_socket.recv(1024).decode('utf-8')
            
            # Send SSE headers
            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/event-stream\r\n"
                "Cache-Control: no-cache\r\n"
                "Connection: keep-alive\r\n"
                "Access-Control-Allow-Origin: *\r\n"
                "\r\n"
            )
            client_socket.send(response.encode('utf-8'))
            
            # Register client
            self._clients[client_id] = client_socket
            self._statistics['total_connections'] += 1
            self._statistics['active_connections'] += 1
            
            self.client_connected.emit(client_id)
            self.logger.info(f"HTTP SSE client connected: {client_id}")
            
            # Keep connection alive
            while self._is_running:
                time.sleep(1.0)
                # Send keep-alive comment
                try:
                    client_socket.send(b": keep-alive\n\n")
                except:
                    break
            
        except Exception as e:
            self.logger.error(f"HTTP SSE client error: {e}")
        finally:
            client_socket.close()
            if client_id in self._clients:
                del self._clients[client_id]
            self._statistics['active_connections'] -= 1
            self.client_disconnected.emit(client_id)
            self.logger.info(f"HTTP SSE client disconnected: {client_id}")
    
    def send_data(self, data: str, client_id: Optional[str] = None) -> None:
        """
        Send data to HTTP SSE clients.
        
        Args:
            data: Serialized data to send
            client_id: Specific client to send to (None = broadcast)
        """
        if not self._is_running or not self._clients:
            return
        
        # Format as SSE message
        sse_message = f"data: {data}\n\n"
        message_bytes = sse_message.encode('utf-8')
        
        try:
            if client_id and client_id in self._clients:
                clients = [(client_id, self._clients[client_id])]
            else:
                clients = list(self._clients.items())
            
            for cid, client_socket in clients:
                try:
                    client_socket.send(message_bytes)
                    self._statistics['total_bytes_sent'] += len(message_bytes)
                    self._statistics['total_messages_sent'] += 1
                    self.data_sent.emit(cid, len(message_bytes))
                except Exception as e:
                    self.logger.error(f"Error sending to HTTP SSE client {cid}: {e}")
            
        except Exception as e:
            self.logger.error(f"Error sending HTTP SSE data: {e}")
            self.error_occurred.emit(str(e))