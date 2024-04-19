# BitcoinTaps - <small>[lnbits](https://github.com/lnbits/lnbits) extension</small>
<small>For BitcoinTaps devices</small>

## Online and offline payments
This extension supports both online and offline Bitcoin Lightning payments. Online payments are processed through regular Lightning invoices and require an internet connection. 
Offline payments, as the name suggests, do not require any internet connection during service, only for the configuration of available products. How does this work? I'll explain. 
When the PartyTap is online and connected to the LNbits server, updates in its configuration (like pricing, tap duration, labels and a shared secret) are directly pushed to the PartyTap, and immediately available. The PartyTap always stores the latest version of this configuration on the device.
When the PartyTap is offline, it uses the latest known configuration. When someone orders a drink, the PartyTap generates a PIN, which is encrypted with the shared secret. This encrypted data is transformed into an LNURL and presented in the form of a QR code. 
The LNbits server adds a note to the Lightning payment that contains a link that, when opened, displays the PIN. Entering the PIN on the the PartyTap will then bring you to the start of the pouring process!

## Operating modes
The PartyTap supports three operating modes: online, offline and auto. 

- In online mode, the PartyTap is only available when there is an active internet connection with its LNbits server. 
- On offline mode, the PartyTap is forced into offline mode, independent of the availabillity of an internet connection. When the PartyTap is connected, updates to product configuration are still pushed to the device, but the payment flow remains the offline variant.
- In auto mode, the PartyTap switches between online and offline payment mode, depending on the availability of an internet connection. If no connection is available, it automatically switches to offline mode. Internet back? then online payment mode is resumed.
-  
