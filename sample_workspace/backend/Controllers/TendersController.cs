using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Authorization;
using SampleApi.Services;
using SampleApi.Entities;

namespace SampleApi.Controllers;

[ApiController]
[Route("api/[controller]")]
[Authorize(Roles = "Admin,TenderManager")]
public class TendersController : ControllerBase
{
    private readonly TenderService _service;

    public TendersController(TenderService service)
    {
        _service = service;
    }

    [HttpGet]
    public async Task<ActionResult<IEnumerable<Tender>>> List()
    {
        return Ok(await _service.ListAsync());
    }

    [HttpPost]
    public async Task<ActionResult<Tender>> Create([FromBody] TenderCreateDto dto)
    {
        var created = await _service.CreateAsync(dto);
        return CreatedAtAction(nameof(List), new { id = created.Id }, created);
    }

    [HttpGet("{id}")]
    public async Task<ActionResult<Tender>> GetById(int id)
    {
        var item = await _service.GetByIdAsync(id);
        if (item == null) return NotFound();
        return Ok(item);
    }
}

public record TenderCreateDto(string Title, string? Description);
