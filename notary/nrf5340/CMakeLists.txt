cmake_minimum_required(VERSION 3.20.0)

# pqm4 ML-DSA-44 as a Zephyr module (modules/pqm4). The pqm4 checkout itself is found via
# PQM4_DIR (env or CMake variable), default <west topdir>/modules/crypto/pqm4.
list(APPEND ZEPHYR_EXTRA_MODULES ${CMAKE_CURRENT_LIST_DIR}/modules/pqm4)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(mosca_notary)

target_sources(app PRIVATE src/main.c)
