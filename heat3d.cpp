/**
 * ============================================================
 *  3D Heat Transfer Simulation (FTCS Finite Difference Method)
 *  Уравнение теплопроводности: dT/dt = alpha * (d²T/dx² + d²T/dy² + d²T/dz²)
 * ============================================================
 *
 *  Все параметры передаются через аргументы командной строки.
 *
 *  Компиляция:
 *    g++ -O2 -std=c++17 -o heat3d heat3d.cpp
 *    (Visual Studio: Ctrl+Shift+B, стандарт C++17)
 *
 *  Запуск вручную:
 *    heat3d.exe --nx 30 --ny 30 --nz 30 --alpha 1.28e-5 --t_end 50000
 *               --t_init 20 --t_boundary 100 --save_every 500
 *
 *  Без аргументов — используются значения по умолчанию (сталь, 30³).
 * ============================================================
 */

#include <iostream>
#include <fstream>
#include <vector>
#include <cmath>
#include <iomanip>
#include <string>
#include <chrono>
#include <stdexcept>
#include <direct.h>   // _mkdir для Windows (вместо filesystem)

// ─── Вспомогательные функции ─────────────────────────────────────────────────
using Grid3D = std::vector<double>;

// Линейный индекс трёхмерного массива
inline int idx(int i, int j, int k, int NY, int NZ) {
    return i * NY * NZ + j * NZ + k;
}

double computeStableDt(double dx, double dy, double dz, double alpha) {
    double inv = 1.0/(dx*dx) + 1.0/(dy*dy) + 1.0/(dz*dz);
    return 0.4 / (2.0 * alpha * inv);
}

double centerTemp(const Grid3D& T, int NX, int NY, int NZ) {
    return T[idx(NX/2, NY/2, NZ/2, NY, NZ)];
}

double meanTemp(const Grid3D& T) {
    double sum = 0.0;
    for (double v : T) sum += v;
    return sum / (double)T.size();
}

void saveSliceZ(const Grid3D& T, int step,
                int NX, int NY, int NZ,
                double dx, double dy,
                const std::string& dir) {
    int k = NZ / 2;
    std::string fname = dir + "/slice_z_step" + std::to_string(step) + ".csv";
    std::ofstream f(fname);
    f << "x,y,T\n";
    for (int i = 0; i < NX; ++i)
        for (int j = 0; j < NY; ++j)
            f << std::fixed << std::setprecision(6)
              << i*dx << "," << j*dy << ","
              << T[idx(i,j,k,NY,NZ)] << "\n";
}

void saveSliceY(const Grid3D& T, int step,
                int NX, int NY, int NZ,
                double dx, double dz,
                const std::string& dir) {
    int j = NY / 2;
    std::string fname = dir + "/slice_y_step" + std::to_string(step) + ".csv";
    std::ofstream f(fname);
    f << "x,z,T\n";
    for (int i = 0; i < NX; ++i)
        for (int k = 0; k < NZ; ++k)
            f << std::fixed << std::setprecision(6)
              << i*dx << "," << k*dz << ","
              << T[idx(i,j,k,NY,NZ)] << "\n";
}

// ─── Парсинг аргументов ───────────────────────────────────────────────────────
struct Params {
    int    nx         = 30;
    int    ny         = 30;
    int    nz         = 30;
    double lx         = 1.0;
    double ly         = 1.0;
    double lz         = 1.0;
    double alpha      = 1.28e-5;
    double t_end      = 50000.0;
    double t_init     = 20.0;
    double t_boundary = 100.0;
    int    save_every = 500;
};

Params parseArgs(int argc, char* argv[]) {
    Params p;
    for (int i = 1; i < argc - 1; ++i) {
        std::string key(argv[i]);
        std::string val(argv[i+1]);
        if      (key == "--nx")         { p.nx         = std::stoi(val); ++i; }
        else if (key == "--ny")         { p.ny         = std::stoi(val); ++i; }
        else if (key == "--nz")         { p.nz         = std::stoi(val); ++i; }
        else if (key == "--lx")         { p.lx         = std::stod(val); ++i; }
        else if (key == "--ly")         { p.ly         = std::stod(val); ++i; }
        else if (key == "--lz")         { p.lz         = std::stod(val); ++i; }
        else if (key == "--alpha")      { p.alpha      = std::stod(val); ++i; }
        else if (key == "--t_end")      { p.t_end      = std::stod(val); ++i; }
        else if (key == "--t_init")     { p.t_init     = std::stod(val); ++i; }
        else if (key == "--t_boundary") { p.t_boundary = std::stod(val); ++i; }
        else if (key == "--save_every") { p.save_every = std::stoi(val); ++i; }
    }
    return p;
}

// ─── Главная функция ─────────────────────────────────────────────────────────
int main(int argc, char* argv[]) {
    using namespace std::chrono;

    Params p = parseArgs(argc, argv);

    // Валидация
    if (p.nx < 3) p.nx = 3;
    if (p.ny < 3) p.ny = 3;
    if (p.nz < 3) p.nz = 3;
    if (p.alpha <= 0) p.alpha = 1.28e-5;
    if (p.t_end <= 0) p.t_end = 1000.0;
    if (p.save_every < 1) p.save_every = 1;

    // Шаги сетки
    const double dx = p.lx / (p.nx - 1);
    const double dy = p.ly / (p.ny - 1);
    const double dz = p.lz / (p.nz - 1);
    const double dt = computeStableDt(dx, dy, dz, p.alpha);
    const int NSTEPS = static_cast<int>(p.t_end / dt) + 1;

    std::cout << "========================================\n";
    std::cout << "  3D Heat Transfer Simulation (FTCS)\n";
    std::cout << "========================================\n";
    std::cout << "  Grid      : " << p.nx << " x " << p.ny << " x " << p.nz << "\n";
    std::cout << "  dx/dy/dz  : " << dx << " / " << dy << " / " << dz << " m\n";
    std::cout << "  alpha     : " << p.alpha << " m^2/s\n";
    std::cout << "  dt        : " << dt << " s  (stable)\n";
    std::cout << "  T_end     : " << p.t_end << " s\n";
    std::cout << "  T_init    : " << p.t_init << " C\n";
    std::cout << "  T_boundary: " << p.t_boundary << " C\n";
    std::cout << "  Steps     : " << NSTEPS << "\n";
    std::cout << "========================================\n\n";

    // Создаём папку output (Windows-совместимо)
    std::string outDir = "output";
    _mkdir(outDir.c_str());

    // Инициализация поля температуры
    const int N = p.nx * p.ny * p.nz;
    Grid3D T(N, p.t_init);
    Grid3D T_new(N, 0.0);

    // Граничные условия Дирихле
    auto applyBC = [&](Grid3D& g) {
        for (int j = 0; j < p.ny; ++j)
            for (int k = 0; k < p.nz; ++k) {
                g[idx(0,       j, k, p.ny, p.nz)] = p.t_boundary;
                g[idx(p.nx-1,  j, k, p.ny, p.nz)] = p.t_boundary;
            }
        for (int i = 0; i < p.nx; ++i)
            for (int k = 0; k < p.nz; ++k) {
                g[idx(i, 0,       k, p.ny, p.nz)] = p.t_boundary;
                g[idx(i, p.ny-1,  k, p.ny, p.nz)] = p.t_boundary;
            }
        for (int i = 0; i < p.nx; ++i)
            for (int j = 0; j < p.ny; ++j) {
                g[idx(i, j, 0,       p.ny, p.nz)] = p.t_boundary;
                g[idx(i, j, p.nz-1,  p.ny, p.nz)] = p.t_boundary;
            }
    };

    applyBC(T);

    // Файл истории
    std::ofstream histFile(outDir + "/history.csv");
    histFile << "step,time,T_center,T_mean\n";

    // Коэффициенты схемы
    const double rx = p.alpha * dt / (dx * dx);
    const double ry = p.alpha * dt / (dy * dy);
    const double rz = p.alpha * dt / (dz * dz);

    std::cout << "  r_x=" << rx << "  r_y=" << ry << "  r_z=" << rz << "\n";
    std::cout << "  Stability sum: " << 2*(rx+ry+rz) << " (must be < 1)\n\n";

    // Временной цикл
    auto t0 = high_resolution_clock::now();
    double time = 0.0;

    for (int step = 0; step <= NSTEPS; ++step) {
        if (step % p.save_every == 0) {
            double Tc    = centerTemp(T, p.nx, p.ny, p.nz);
            double Tmean = meanTemp(T);

            histFile << step << "," << std::fixed << std::setprecision(4)
                     << time << "," << Tc << "," << Tmean << "\n";
            histFile.flush();

            saveSliceZ(T, step, p.nx, p.ny, p.nz, dx, dy, outDir);
            saveSliceY(T, step, p.nx, p.ny, p.nz, dx, dz, outDir);

            std::cout << "  step=" << std::setw(6) << step
                      << "  t=" << std::setw(10) << std::fixed
                      << std::setprecision(2) << time << " s"
                      << "  T_center=" << std::setw(8)
                      << std::setprecision(3) << Tc << " C"
                      << "  T_mean=" << std::setw(8)
                      << std::setprecision(3) << Tmean << " C\n";
            std::cout.flush();
        }

        if (step == NSTEPS) break;

        // FTCS шаг
        for (int i = 1; i < p.nx-1; ++i) {
            for (int j = 1; j < p.ny-1; ++j) {
                for (int k = 1; k < p.nz-1; ++k) {
                    double Tijk = T[idx(i,  j,  k,   p.ny, p.nz)];
                    double d2x  = T[idx(i+1,j,  k,   p.ny, p.nz)]
                                - 2*Tijk
                                + T[idx(i-1,j,  k,   p.ny, p.nz)];
                    double d2y  = T[idx(i,  j+1,k,   p.ny, p.nz)]
                                - 2*Tijk
                                + T[idx(i,  j-1,k,   p.ny, p.nz)];
                    double d2z  = T[idx(i,  j,  k+1, p.ny, p.nz)]
                                - 2*Tijk
                                + T[idx(i,  j,  k-1, p.ny, p.nz)];
                    T_new[idx(i,j,k,p.ny,p.nz)] = Tijk + rx*d2x + ry*d2y + rz*d2z;
                }
            }
        }

        applyBC(T_new);
        std::swap(T, T_new);
        time += dt;
    }

    auto t1 = high_resolution_clock::now();
    double elapsed = duration_cast<milliseconds>(t1 - t0).count() / 1000.0;

    std::cout << "\n  Simulation done in " << elapsed << " s\n";
    std::cout << "  Output saved to: ./" << outDir << "/\n";
    return 0;
}
