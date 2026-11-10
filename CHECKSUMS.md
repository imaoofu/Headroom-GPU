# Byte checksums

Copied files are byte-for-byte filesystem reads from the recorded working tree. No BOM, encoding, CRLF, LF or lone-CR normalization is applied. SHA-256 hashes the exact distributed bytes, not Git blobs or a line-ending-neutral representation. Generated text is UTF-8 without BOM; JSON/Markdown/CFF use LF and manifest CSV uses CRLF. SHA256SUMS covers every distributed file except itself, including the review report.
