// SPDX-FileCopyrightText: Copyright (C) Arduino s.r.l. and/or its affiliated companies
// SPDX-License-Identifier: MPL-2.0
// (Re-created from the App Lab 0.12 WebUI brick template.)

class WebUI {
  #socket;

  constructor(options = {}) {
    this.#socket = io(`http://${window.location.host}`, options);
  }

  /** Called when the websocket connects to the server. */
  on_connect(callback) {
    this.#socket.on('connect', callback);
  }

  /** Called when the websocket disconnects from the server. */
  on_disconnect(callback) {
    this.#socket.on('disconnect', callback);
  }

  /** Registers a callback for a specific event message from the board. */
  on_message(eventName, callback) {
    this.#socket.on(eventName, callback);
  }

  /** Sends a message to the board for a specific event. */
  send_message(eventName, data) {
    this.#socket.emit(eventName, data ?? {});
  }
}
