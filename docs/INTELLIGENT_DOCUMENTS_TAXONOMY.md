# ORA — Document taxonomy

Estensibile. Nuove sottocategorie si aggiungono in `backend/documents/intelligence/taxonomy.py` senza riscrivere la pipeline.

## Macro

`event`, `education`, `work`, `administrative`, `financial`, `medical`, `travel`, `legal`, `receipt`, `contract`, `certificate`, `identity`, `personal`, `generic`, `unknown`

## Sotto (esempi)

medical_appointment, cinema_ticket, concert_ticket, exhibition_ticket, train_ticket, flight_booking, hotel_booking, university_exam, lesson, school_notes, university_notes, lecture_slides, invoice, tax_document, insurance, warranty, official_notice, prescription, medical_report, employment_contract, rental_contract, purchase_receipt, generic

## Mapping legacy

I `type_key` del classifier deterministico (`ticket`, `invoice`, …) sono mappati a macro/sub e poi raffinati con euristiche testuali.
