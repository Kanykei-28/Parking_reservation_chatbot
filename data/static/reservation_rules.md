# Reservation rules

## Booking period

A reservation can be created up to 5 days in advance. The minimum duration is 1
hour, and the maximum duration is 15 hours. The reservation must be within
working hours.

## Required details

The user must provide:

- First name
- Surname
- Car number
- Parking type
- Start date and time
- End date and time

## Status

Every new reservation has the status `pending`. An administrator then changes
the status to `approved` or `rejected`.

## Cancellation and late arrival

A reservation can be cancelled before its start time. The reserved space is
released if the driver is more than 15 minutes late.

## Fully booked parking

A reservation request must not be sent to the administrator when the selected
parking type is fully booked for the requested period.
