using SampleApi.Entities;
using SampleApi.Controllers;

namespace SampleApi.Services;

public class TenderService
{
    private readonly ITenderRepository _repo;

    public TenderService(ITenderRepository repo)
    {
        _repo = repo;
    }

    public Task<List<Tender>> ListAsync() => _repo.ListAsync();

    public Task<Tender?> GetByIdAsync(int id) => _repo.GetByIdAsync(id);

    public async Task<Tender> CreateAsync(TenderCreateDto dto)
    {
        var entity = new Tender
        {
            Title = dto.Title,
            Description = dto.Description,
            Status = "Draft",
        };
        return await _repo.AddAsync(entity);
    }
}

public interface ITenderRepository
{
    Task<List<Tender>> ListAsync();
    Task<Tender?> GetByIdAsync(int id);
    Task<Tender> AddAsync(Tender tender);
}
